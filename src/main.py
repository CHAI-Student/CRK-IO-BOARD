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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from uvicorn.config import Config
from uvicorn.server import Server

from api.v1.routers import machine, management, recording, sse
from core.config import Settings
from core.logging_config import (
    PerformanceLogger,
    clear_correlation_id,
    get_logger,
    set_correlation_id,
    setup_logging,
)
from exceptions import IOBoardError
from services.polling import data_sources, polling_service
from services.io_board.serial_io import configure_serial

logger = get_logger(__name__)

# Shared shutdown signal for cooperative streaming stop
stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""

    app.state.stop_event = stop_event

    settings = app.state.settings

    setup_logging(settings.api.log_level.upper())

    configure_serial(settings.serial)

    loadcells_data_source = data_sources.LoadCellsDataSource()
    loadcells_polling_service = polling_service.PollingService(
        data_source=loadcells_data_source,
        interval=settings.polling.loadcells_poll_interval,
        name="LoadCells",
    )
    io_status_data_source = data_sources.IOStatusDataSource()
    io_status_polling_service = polling_service.PollingService(
        data_source=io_status_data_source,
        interval=settings.polling.io_status_poll_interval,
        name="IOStatus",
    )

    app.state.polling_services = {
        "loadcells": loadcells_polling_service,
        "io_status": io_status_polling_service,
    }

    import services.recording as recording
    import services.error_state_mgmt as error_state_mgmt

    loadcells_recording_service = recording.RecordingService(
        polling_service=loadcells_polling_service,
        name="LoadCellsRecording",
    )

    error_state_management_service = error_state_mgmt.ErrorStateManagementService(
        polling_service=io_status_polling_service,
        name="ErrorStateManagement",
    )

    app.state.recording_services = {
        "loadcells": loadcells_recording_service,
        "error_state_management": error_state_management_service,
    }

    # Start polling services
    await loadcells_polling_service.start()
    await io_status_polling_service.start()

    # Start recording services
    await loadcells_recording_service.start()
    await error_state_management_service.start()
    try:
        yield
    finally:
        # Stop recording services
        await loadcells_recording_service.stop()
        await error_state_management_service.stop()
        # Stop polling services
        await loadcells_polling_service.stop()
        await io_status_polling_service.stop()
        logger.info("IO Board Control Service Stopped")


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


#####################
# Graceful Shutdown #
#####################


class GracefulShutdownServer(Server):
    """Uvicorn server subclass that handles graceful shutdown."""

    async def shutdown(self, *args, **kwargs) -> None:
        """Handle server shutdown by setting the stop event."""
        logger.info("Server shutdown initiated, stopping services...")
        stop_event.set()
        await super().shutdown(*args, **kwargs)


if __name__ == "__main__":
    settings = app.state.settings = Settings()

    config = Config(
        app,
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.api.log_level,
        timeout_graceful_shutdown=settings.api.timeout_graceful_shutdown,
    )

    server = GracefulShutdownServer(config=config)

    try:
        server.run()
    except KeyboardInterrupt:
        pass

else:
    # To support graceful shutdown, It is mandatory to replace uvicorn server implementation
    # So if this module is imported, we exit with an error
    print("This module is intended to be run as the main program.")
    exit(1)
