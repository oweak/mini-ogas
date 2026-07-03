from fastapi import APIRouter

from ..store import store
from . import (
    ai,
    audit,
    compat,
    control,
    demo,
    dispatch,
    health,
    history,
    market,
    nodes,
    ops,
    preflight,
    production,
    replay,
    reports,
    simulation,
    transfer,
)

api_router = APIRouter()
api_router.include_router(preflight.router)
api_router.include_router(compat.router)
api_router.include_router(health.router)
api_router.include_router(history.router)
api_router.include_router(ops.router)
api_router.include_router(nodes.router)
api_router.include_router(dispatch.router)
api_router.include_router(market.router)
api_router.include_router(production.router)
api_router.include_router(replay.router)
api_router.include_router(reports.router)
api_router.include_router(ai.router)
api_router.include_router(audit.router)
api_router.include_router(simulation.router)
api_router.include_router(demo.router)
api_router.include_router(transfer.router)
api_router.include_router(control.router)


@api_router.get("/management/snapshot")
def management_snapshot():
    return store.management_snapshot()
