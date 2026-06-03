import base64
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..models import TransferDataTestIn, TransferFileTestIn, TransferTestResult
from ..store import store

router = APIRouter(prefix="/transfer", tags=["transfer"])

_path = Path(__file__).resolve()
try:
    PROJECT_ROOT = _path.parents[4]
except IndexError:
    PROJECT_ROOT = _path.parents[3]
TRANSFER_DIR = PROJECT_ROOT / ".runtime" / "transfers"


def _route(target_node: str) -> list[str]:
    return ["dashboard", "central-api", target_node]


def _ensure_target_node(target_node: str) -> None:
    if target_node not in store.nodes:
        raise HTTPException(status_code=404, detail=f"target node not found: {target_node}")


@router.post("/data-test", response_model=TransferTestResult)
def data_transfer_test(payload: TransferDataTestIn) -> TransferTestResult:
    _ensure_target_node(payload.target_node)
    raw = json.dumps(payload.model_dump(), ensure_ascii=False, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    TRANSFER_DIR.mkdir(parents=True, exist_ok=True)
    saved_to = (TRANSFER_DIR / f"data-{payload.batch_id}.json").resolve()
    if not str(saved_to).startswith(str(TRANSFER_DIR.resolve())):
        raise HTTPException(status_code=400, detail="invalid batch_id path")
    saved_to.write_bytes(raw)
    return TransferTestResult(
        accepted=True,
        transfer_type="json-data",
        target_node=payload.target_node,
        route=_route(payload.target_node),
        bytes_received=len(raw),
        checksum_sha256=checksum,
        saved_to=str(saved_to),
        message=f"received {len(payload.records)} records for {payload.target_node}",
    )


@router.post("/file-test", response_model=TransferTestResult)
def file_transfer_test(payload: TransferFileTestIn) -> TransferTestResult:
    _ensure_target_node(payload.target_node)
    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="content_base64 is not valid base64") from exc
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="test file is limited to 2MB")

    checksum = hashlib.sha256(raw).hexdigest()
    TRANSFER_DIR.mkdir(parents=True, exist_ok=True)
    saved_to = (TRANSFER_DIR / payload.file_name).resolve()
    # Defense-in-depth: ensure the resolved path stays within TRANSFER_DIR
    if not str(saved_to).startswith(str(TRANSFER_DIR.resolve())):
        raise HTTPException(status_code=400, detail="invalid file path")
    saved_to.write_bytes(raw)
    return TransferTestResult(
        accepted=True,
        transfer_type="base64-file",
        target_node=payload.target_node,
        route=_route(payload.target_node),
        bytes_received=len(raw),
        checksum_sha256=checksum,
        saved_to=str(saved_to),
        message=f"received file {payload.file_name} for {payload.target_node}",
    )
