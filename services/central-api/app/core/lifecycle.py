import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..repositories.data_platform import data_platform_repository
from ..store import store
from .auth import initialize_auth_store
from .config import settings
from .nats_contracts import TransportEnvelope
from .nats_publisher import nats_runtime
from .outbox import outbox_repository

logger = logging.getLogger("mini_ogas.central_api")


async def simulation_loop() -> None:
    while True:
        try:
            if store.simulation_running:
                await asyncio.to_thread(store.simulation_step)
            speed = max(store.simulation_speed, 0.2)  # guard against zero/negative
            interval = max(
                settings.simulation_min_interval_seconds,
                settings.simulation_base_interval_seconds / speed,
            )
            await asyncio.sleep(interval)
        except Exception:
            logger.exception(
                "simulation_loop: unhandled error — will retry after delay")
            await asyncio.sleep(settings.simulation_base_interval_seconds)


async def heartbeat_monitor() -> None:
    """Periodically scan nodes for heartbeat timeout and mark stale nodes offline."""
    while True:
        await asyncio.sleep(settings.heartbeat_timeout_seconds / 3)
        try:
            expired = await asyncio.to_thread(store.check_heartbeat_timeout)
            if expired:
                logger.warning(
                    "heartbeat monitor: %d node(s) marked offline due to timeout", expired)
        except Exception:
            logger.exception(
                "heartbeat monitor: unhandled error during timeout check")


async def outbox_publish_loop() -> None:
    while True:
        try:
            if not settings.persist_enabled or not settings.nats_enabled:
                await asyncio.sleep(settings.nats_retry_seconds)
                continue
            messages = await asyncio.to_thread(outbox_repository.claim_pending, limit=50)
            if not messages:
                await asyncio.sleep(0.5)
                continue
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
                    continue
                result = await nats_runtime.publish_envelope(envelope)
                if result.status == "published":
                    await asyncio.to_thread(outbox_repository.mark_published, message_id)
                elif attempts >= 10:
                    await asyncio.to_thread(
                        outbox_repository.mark_dead_letter,
                        message_id,
                        result.error_category or result.status,
                    )
                else:
                    await asyncio.to_thread(
                        outbox_repository.mark_failed,
                        message_id,
                        result.error_category or result.status,
                        attempts,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("outbox_publish_loop: publish cycle failed")
            await asyncio.sleep(settings.nats_retry_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(initialize_auth_store)
    if settings.telemetry_bootstrap_catalog_enabled:
        provisioned = await asyncio.to_thread(
            data_platform_repository.provision_digital_twin_catalog,
            "system:data-platform-bootstrap",
        )
        logger.info("Phase 7 digital-twin catalog provisioned: %s", provisioned)
    await nats_runtime.start()
    sim_task = asyncio.create_task(simulation_loop())
    hb_task = asyncio.create_task(heartbeat_monitor())
    outbox_task = asyncio.create_task(outbox_publish_loop())
    try:
        yield
    finally:
        for task in (sim_task, hb_task, outbox_task):
            task.cancel()
        for task in (sim_task, hb_task, outbox_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await nats_runtime.stop()
