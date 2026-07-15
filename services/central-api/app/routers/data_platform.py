from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from ..core.errors import problem_response
from ..core.object_storage import document_object_storage
from ..core.redis_projection import redis_telemetry_projection
from ..core.security import (
    PERM_DOCUMENT_OBJECT_MANAGE,
    PERM_PROJECTION_REBUILD,
    PERM_TELEMETRY_INGEST,
    PERM_TELEMETRY_MANAGE,
    PERM_TELEMETRY_READ,
    PERM_TELEMETRY_RETENTION,
    ActorInfo,
    require_permission,
)
from ..domain.data_platform import (
    AggregateTelemetryIn,
    DataPlatformError,
    ProjectionRebuildIn,
    RetentionRunIn,
    SignalDefinitionIn,
    TelemetryBatchIn,
)
from ..repositories.data_platform import data_platform_repository

router = APIRouter(tags=["data-platform"])
TelemetryManager = Depends(require_permission(PERM_TELEMETRY_MANAGE))
TelemetryIngester = Depends(require_permission(PERM_TELEMETRY_INGEST))
TelemetryReader = Depends(require_permission(PERM_TELEMETRY_READ))
ProjectionManager = Depends(require_permission(PERM_PROJECTION_REBUILD))
RetentionManager = Depends(require_permission(PERM_TELEMETRY_RETENTION))
ObjectManager = Depends(require_permission(PERM_DOCUMENT_OBJECT_MANAGE))


def _actor_name(actor: ActorInfo) -> str:
    return actor.username or actor.display_name or actor.role


def _problem(request: Request, exc: DataPlatformError):
    return problem_response(
        request,
        exc.status_code,
        {"message": exc.message, **exc.context},
        code=exc.code,
    )


@router.post("/telemetry/signals", status_code=status.HTTP_201_CREATED)
def create_signal(
    payload: SignalDefinitionIn,
    request: Request,
    actor: ActorInfo = TelemetryManager,
):
    try:
        return data_platform_repository.create_signal(payload, _actor_name(actor))
    except DataPlatformError as exc:
        return _problem(request, exc)


@router.get("/telemetry/signals")
def list_signals(actor: ActorInfo = TelemetryReader):
    del actor
    return {"signals": data_platform_repository.list_signals()}


@router.post("/telemetry/batches", status_code=status.HTTP_201_CREATED)
def ingest_batch(
    payload: TelemetryBatchIn,
    request: Request,
    response: Response,
    actor: ActorInfo = TelemetryIngester,
):
    try:
        result, replayed = data_platform_repository.ingest_batch(payload, _actor_name(actor))
    except DataPlatformError as exc:
        return _problem(request, exc)
    response.status_code = status.HTTP_200_OK if replayed else status.HTTP_201_CREATED
    return result


@router.get("/telemetry/latest")
def latest_signals(actor: ActorInfo = TelemetryReader):
    del actor
    return data_platform_repository.latest_signals()


@router.get("/telemetry/quality/summary")
def quality_summary(actor: ActorInfo = TelemetryReader):
    del actor
    return data_platform_repository.quality_summary()


@router.post("/telemetry/aggregate/hourly", include_in_schema=False)
@router.post("/telemetry/aggregations/hourly")
def aggregate_hourly(
    payload: AggregateTelemetryIn,
    actor: ActorInfo = TelemetryManager,
):
    del actor
    return data_platform_repository.aggregate_hourly(payload)


@router.post("/telemetry/retention/run")
def run_retention(
    payload: RetentionRunIn,
    request: Request,
    actor: ActorInfo = RetentionManager,
):
    try:
        return data_platform_repository.run_retention(
            reason=payload.reason,
            actor=_actor_name(actor),
        )
    except DataPlatformError as exc:
        return _problem(request, exc)


@router.post("/telemetry/projection/rebuild")
def rebuild_projection(
    payload: ProjectionRebuildIn,
    request: Request,
    actor: ActorInfo = ProjectionManager,
):
    try:
        return redis_telemetry_projection.rebuild(payload.reason, _actor_name(actor))
    except DataPlatformError as exc:
        return _problem(request, exc)


@router.get("/telemetry/projection/status")
def projection_status(
    request: Request,
    actor: ActorInfo = TelemetryReader,
):
    del actor
    try:
        return redis_telemetry_projection.status()
    except DataPlatformError as exc:
        return _problem(request, exc)


@router.put("/document-objects/{original_name}", status_code=status.HTTP_201_CREATED)
async def put_document_object(
    original_name: str,
    request: Request,
    actor: ActorInfo = ObjectManager,
):
    content = await request.body()
    try:
        return document_object_storage.store(
            original_name=original_name,
            content=content,
            content_type=request.headers.get("content-type", "application/octet-stream"),
            expected_sha256=request.headers.get("x-content-sha256", ""),
            actor=_actor_name(actor),
        )
    except DataPlatformError as exc:
        return _problem(request, exc)


@router.get("/document-objects/{object_id}")
def get_document_object(
    object_id: int,
    request: Request,
    actor: ActorInfo = ObjectManager,
):
    try:
        content, manifest = document_object_storage.retrieve(
            object_id=object_id,
            actor=_actor_name(actor),
        )
    except DataPlatformError as exc:
        return _problem(request, exc)
    return Response(
        content=content,
        media_type=str(manifest["content_type"]),
        headers={
            "X-Content-SHA256": str(manifest["content_sha256"]),
            "X-Object-Integrity": "verified",
            "X-Object-Id": str(manifest["id"]),
            "Cache-Control": "no-store",
        },
    )
