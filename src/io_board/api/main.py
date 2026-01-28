"""
FastAPI REST API for IO Board device control.

This module provides a RESTful API interface to the IO Board device with:
- Comprehensive endpoint documentation
- Standard error responses
- Request/response validation
- Structured logging
- Correlation ID tracking
"""

import asyncio
import json
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from uvicorn.config import Config as UvicornConfig
from uvicorn.server import Server

from io_board.api.routers import machine, management, recording

from .routers import sse

from ..config import APIConfig
from ..exceptions import IOBoardError
from ..logging_config import (
    PerformanceLogger,
    get_logger,
    set_correlation_id,
    clear_correlation_id,
)


logger = get_logger(__name__)

# Shared shutdown signal for cooperative streaming stop
stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register signal handlers and expose stop flag on app state."""
    loop = asyncio.get_running_loop()

    def _set_stop_event() -> None:
        stop_event.set()

    # Register OS signal handlers where supported
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _set_stop_event)
        except (NotImplementedError, RuntimeError):
            # Windows or non-main thread may not support signal handlers
            pass

    app.state.stop_event = stop_event

    try:
        yield
    finally:
        stop_event.set()


app = FastAPI(
    title="IO Board Control API",
    description="REST API for controlling IO Board device with loadcells, door locks, and sensors",
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Middleware for request/response logging with correlation IDs.

    Logs all incoming requests and outgoing responses with timing information
    and correlation IDs for request tracing.
    """
    # Generate correlation ID for this request
    correlation_id = set_correlation_id()

    # Log incoming request
    logger.info(
        f"Request started: method={request.method} path={request.url.path} "
        f"client={request.client.host if request.client else 'unknown'}"
    )

    # Log request body for POST/PUT/PATCH
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.body()
            if body:
                logger.debug(f"Request body: {body.decode('utf-8')}")
        except Exception:
            pass

    # Process request and measure time
    try:
        with PerformanceLogger(logger, "request", path=request.url.path):
            response = await call_next(request)

        # Log response
        logger.info(f"Request completed: status={response.status_code}")

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response
    finally:
        clear_correlation_id()


@app.exception_handler(IOBoardError)
async def ioboard_error_handler(request: Request, exc: IOBoardError) -> JSONResponse:
    """
    Global exception handler for IO Board errors.

    Converts all IOBoardError exceptions to standard JSON error responses.
    """
    logger.error(
        f"IO Board error: {exc.error_code.value} - {exc.message}", exc_info=exc
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=exc.to_dict(),
    )


@app.exception_handler(PydanticValidationError)
async def validation_error_handler(
    request: Request, exc: PydanticValidationError
) -> JSONResponse:
    """
    Global exception handler for Pydantic validation errors.

    Converts validation errors to standard JSON error responses.
    """
    logger.warning(f"Validation error: {exc.errors()}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "E4001",
            "message": "Request validation failed",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for unexpected errors.

    Logs the full exception and returns a generic error response
    without leaking internal details.
    """
    logger.error(f"Unexpected error: {exc}", exc_info=exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "E9001",
            "message": "Internal server error",
            "details": {},
        },
    )


app.include_router(management.router)
app.include_router(machine.router)
app.include_router(recording.router)
app.include_router(sse.router)

# ============================================================================
# Graceful Server
# ============================================================================


class GracefulServer(Server):
    """
    Uvicorn server with external shutdown event support.

    Extends Uvicorn's Server to monitor an external asyncio.Event for
    graceful shutdown coordination across multiple services.
    """

    def __init__(self, config: UvicornConfig, shutdown_event: asyncio.Event):
        """
        Initialize graceful server.

        Args:
            config: Uvicorn server configuration
            shutdown_event: External shutdown event to monitor
        """
        super().__init__(config)
        self._external_shutdown = shutdown_event
        self.force_exit = False  # Graceful shutdown, wait for requests

    async def serve(self, sockets=None):
        """
        Override serve to monitor external shutdown event.

        Args:
            sockets: Optional pre-bound sockets
        """
        # Start shutdown monitor task
        monitor_task = asyncio.create_task(self._monitor_shutdown())
        try:
            await super().serve(sockets)
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_shutdown(self):
        """Monitor external shutdown event and trigger server shutdown."""
        await self._external_shutdown.wait()
        logger.info("External shutdown signal received, stopping API server")
        self.should_exit = True

    async def shutdown(self, sockets=None):
        """
        Override shutdown to set external shutdown event.

        Args:
            sockets: Optional pre-bound sockets
        """
        self._external_shutdown.set()
        await super().shutdown(sockets)


async def serve_api(config: APIConfig, polling_services: dict, recording_services: dict) -> None:
    """
    Start the FastAPI server.

    Args:
        config: API configuration object
        polling_services: Dictionary of polling service instances
        recording_services: Dictionary of recording service instances
    """
    # Store config in app state for access by handlers
    app.state.stream_interval = config.stream_interval
    app.state.polling_services = polling_services
    app.state.recording_services = recording_services

    logger.info(
        f"Starting API server: host={config.host} port={config.port} "
        f"log_level={config.log_level}"
    )

    uvicorn_config = UvicornConfig(
        app=app,
        host=config.host,
        port=config.port,
        log_level=config.log_level,
    )
    server = GracefulServer(uvicorn_config, stop_event)

    await server.serve()
