from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..store import store

router = APIRouter(tags=["replay"])


@router.get("/api/replay/runs")
@router.get("/replay/runs")
def replay_runs(
    limit: int = Query(default=20, ge=1, le=100),
    max_rows: int = Query(default=1000, ge=1, le=10000),
) -> dict[str, object]:
    """List persisted run_id batches available for operational replay."""
    return store.replay_runs(limit=limit, max_rows=max_rows)


@router.get("/api/replay/runs/{run_id}")
@router.get("/replay/runs/{run_id}")
def replay_run(
    run_id: str,
    max_rows: int = Query(default=500, ge=1, le=5000),
) -> dict[str, object]:
    """Return a persisted operational timeline for a specific run_id."""
    result = store.replay_run(run_id, max_rows=max_rows)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")
    return result
