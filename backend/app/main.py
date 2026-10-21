import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import get_settings
from app.logging_setup import configure_logging
from app.routers import health, meta

log = logging.getLogger("floodsense")


def _err(status: int, code: str, message: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": code, "message": message, "request_id": getattr(request.state, "request_id", None)},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="FloodSense API", version=__version__,
        description="Advisory flood-risk estimation and routing. Not an official warning system.",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        return _err(exc.status_code, "http_error", str(exc.detail), request)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []))
        return _err(422, "validation_error", f"{loc}: {first.get('msg', 'invalid request')}", request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return _err(500, "internal_error", "An internal error occurred.", request)

    app.include_router(health.router)
    app.include_router(meta.router)
    return app


app = create_app()
