import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.lifecycle import lifespan
from .core.security import security_middleware
from .routers import api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mini_ogas.central_api")


def _development_error_detail(exc: Exception) -> dict[str, str]:
    return {"detail": str(exc), "error_type": exc.__class__.__name__}


def _is_development() -> bool:
    return os.getenv("MINI_OGAS_ENV", "").lower() == "development"


def setup_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:5174", "http://127.0.0.1:5174",
            "http://localhost:5175", "http://127.0.0.1:5175",
            "http://localhost:5176", "http://127.0.0.1:5176",
            "http://localhost:5177", "http://127.0.0.1:5177",
            "http://localhost:3000", "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-OGAS-Token"],
    )

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "method=%s path=%s status_code=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    app.middleware("http")(security_middleware)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
        content = _development_error_detail(exc) if _is_development() else {"detail": "Internal server error"}
        return JSONResponse(status_code=500, content=content)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        content = _development_error_detail(exc) if _is_development() else {"detail": "Internal server error"}
        return JSONResponse(status_code=500, content=content)


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
        dist = Path(__file__).resolve().parents[3] / "services" / "dashboard" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="dashboard")


app = create_app()
