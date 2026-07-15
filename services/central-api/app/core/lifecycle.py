from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .auth import initialize_auth_store
from .nats_publisher import nats_runtime


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize request-serving dependencies without owning periodic work."""
    await asyncio.to_thread(initialize_auth_store)
    await nats_runtime.publisher.start()
    try:
        yield
    finally:
        await nats_runtime.publisher.stop()
