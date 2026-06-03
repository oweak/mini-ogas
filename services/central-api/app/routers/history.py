from fastapi import APIRouter, Query

from ..store import store

router = APIRouter(tags=["history"])


@router.get("/metrics/history")
def metrics_history(
    node_code: str = Query(..., description="Node code to fetch history for"),
    limit: int = Query(default=30, ge=1, le=300),
):
    node_metrics = [m for m in store.metrics if m.node_code == node_code]
    return node_metrics[-limit:]
