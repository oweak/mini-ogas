import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..store import store
from .auth import initialize_auth_store
from .config import settings

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(initialize_auth_store)
    sim_task = asyncio.create_task(simulation_loop())
    hb_task = asyncio.create_task(heartbeat_monitor())
    try:
        yield
    finally:
        for task in (sim_task, hb_task):
            task.cancel()
        for task in (sim_task, hb_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
