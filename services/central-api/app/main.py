import logging
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.errors import problem_response
from .core.identity import REQUEST_ID_HEADER, request_id_for
from .core.lifecycle import lifespan
from .core.security import security_middleware
from .routers import api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mini_ogas.central_api")


def _is_development() -> bool:
    return settings.app_env == "development"


def setup_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-OGAS-Token",
            "X-Content-SHA256",
            REQUEST_ID_HEADER,
        ],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.perf_counter()
        request_id = request_id_for(request)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    app.middleware("http")(security_middleware)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
        return problem_response(request, exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
        return problem_response(request, 422, exc.errors(), code="VALIDATION_ERROR")

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> Response:
        return problem_response(request, 400, str(exc), code="INVALID_ARGUMENT")

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(request: Request, exc: RuntimeError) -> Response:
        detail = str(exc) if _is_development() else "Internal server error"
        return problem_response(request, 500, detail, code="INTERNAL_ERROR")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
        detail = str(exc) if _is_development() else "Internal server error"
        return problem_response(request, 500, detail, code="INTERNAL_ERROR")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    setup_middleware(app)
    app.include_router(api_router)
    _mount_dashboard(app)
    return app


def _mount_dashboard(app: FastAPI) -> None:
    """Serve the Vue dashboard static files when present."""
    if getattr(sys, "frozen", False):
        dist = Path(sys._MEIPASS) / "dashboard-dist"
    else:
        # Development: .../services/central-api/app/main.py → parents[3] = project root
        module_path = Path(__file__).resolve()
        if len(module_path.parents) > 3:
            dist = module_path.parents[3] / "services" / "dashboard" / "dist"
        else:
            # Container layout: /app/app/main.py with an optional bundled dashboard.
            dist = module_path.parents[1] / "dashboard-dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="dashboard")


app = create_app()
