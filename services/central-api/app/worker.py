from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .core.config import settings
from .core.nats_contracts import TransportEnvelope
from .core.nats_publisher import nats_runtime
from .core.nats_reconciliation import nats_shadow_reconciler
from .core.outbox import outbox_repository
from .core.session import get_process_identity, get_session_token
from .repositories.data_platform import data_platform_repository
from .store import store

logger = logging.getLogger("mini_ogas.background_worker")
_tasks: dict[str, asyncio.Task[None]] = {}


class SimulationConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    running: bool | None = None
    speed: float | None = Field(default=None, gt=0, le=20)
    anomaly_rate: float | None = Field(default=None, ge=0, le=1)


def require_internal_token(x_ogas_token: str = Header(default="")) -> None:
    if settings.api_access_token and x_ogas_token != settings.api_access_token:
        raise HTTPException(status_code=401, detail="invalid internal service token")


async def simulation_loop() -> None:
    while True:
        try:
            if store.simulation_running:
                await asyncio.to_thread(store.simulation_step)
            speed = max(store.simulation_speed, 0.2)
            interval = max(
                settings.simulation_min_interval_seconds,
                settings.simulation_base_interval_seconds / speed,
            )
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("simulation loop failed; retrying")
            await asyncio.sleep(settings.simulation_base_interval_seconds)


async def publish_outbox_batch(*, limit: int = 50) -> dict[str, int]:
    result_counts = {"claimed": 0, "published": 0, "retried": 0, "dead_lettered": 0}
    messages = await asyncio.to_thread(outbox_repository.claim_pending, limit=limit)
    result_counts["claimed"] = len(messages)
    for message in messages:
        message_id = str(message["message_id"])
        attempts = int(message["attempts"])
        try:
            envelope = TransportEnvelope.model_validate(message["payload"])
        except Exception as exc:
            await asyncio.to_thread(
                outbox_repository.mark_dead_letter,
                message_id,
                f"invalid outbox envelope: {type(exc).__name__}",
            )
            result_counts["dead_lettered"] += 1
            continue
        publish_result = await nats_runtime.publish_envelope(envelope)
        if publish_result.status == "published":
            await asyncio.to_thread(outbox_repository.mark_published, message_id)
            result_counts["published"] += 1
        elif attempts >= 10:
            await asyncio.to_thread(
                outbox_repository.mark_dead_letter,
                message_id,
                publish_result.error_category or publish_result.status,
            )
            result_counts["dead_lettered"] += 1
        else:
            await asyncio.to_thread(
                outbox_repository.mark_failed,
                message_id,
                publish_result.error_category or publish_result.status,
                attempts,
            )
            result_counts["retried"] += 1
    return result_counts


async def outbox_publish_loop() -> None:
    while True:
        try:
            if not settings.persist_enabled or not settings.nats_enabled:
                await asyncio.sleep(settings.nats_retry_seconds)
                continue
            cycle = await publish_outbox_batch(limit=50)
            if not cycle["claimed"]:
                await asyncio.sleep(0.5)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("outbox publish cycle failed")
            await asyncio.sleep(settings.nats_retry_seconds)


@asynccontextmanager
async def worker_lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.telemetry_bootstrap_catalog_enabled:
        provisioned = await asyncio.to_thread(
            data_platform_repository.provision_digital_twin_catalog,
            "system:data-platform-bootstrap",
        )
        logger.info("digital-twin catalog provisioned: %s", provisioned)
    await nats_runtime.start()
    _tasks["simulation"] = asyncio.create_task(simulation_loop())
    _tasks["outbox"] = asyncio.create_task(outbox_publish_loop())
    try:
        yield
    finally:
        tasks = list(_tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        _tasks.clear()
        await nats_runtime.stop()


app = FastAPI(
    title="Mini-OGAS Background Worker",
    version=settings.version,
    lifespan=worker_lifespan,
)


@app.get("/health")
def health() -> dict[str, object]:
    task_status = {
        name: "running" if not task.done() else "failed" for name, task in _tasks.items()
    }
    nats = nats_runtime.health()
    reconciliation = nats_shadow_reconciler.report(enabled=bool(nats["enabled"]))
    nats["reconciliation"] = reconciliation
    ready = bool(task_status) and all(status == "running" for status in task_status.values())
    if nats["enabled"] and nats["status"] != "live":
        ready = False
    if reconciliation["status"] in {"degraded", "unavailable"}:
        ready = False
    return {
        "status": "ok",
        "overall_status": "ready" if ready else "degraded",
        "service": "background-worker",
        "session_token": get_session_token(),
        "task_owner": "dedicated-process",
        "tasks": task_status,
        "nats": nats,
        **get_process_identity(),
    }


@app.get("/simulation/state", dependencies=[Depends(require_internal_token)])
def simulation_state():
    return store.simulation_state()


@app.post("/simulation/configure", dependencies=[Depends(require_internal_token)])
def configure_simulation(payload: SimulationConfigIn):
    return store.configure_simulation(
        running=payload.running,
        speed=payload.speed,
        anomaly_rate=payload.anomaly_rate,
    )


@app.post("/simulation/step", dependencies=[Depends(require_internal_token)])
def step_simulation():
    return store.simulation_step()
