"""IO Board 디바이스 제어용 FastAPI 서비스 진입점.

애플리케이션 lifespan에서 serial/sanitizer/throttle을 설정하고
polling·recording·error state management 서비스를 기동한다. 제공 기능:
- 표준 에러 응답과 request/response 검증
- correlation ID 추적이 포함된 구조화 로깅
- SSE streaming을 위한 graceful shutdown (uvicorn Server 교체)

주의: graceful shutdown을 위해 uvicorn Server 구현을 교체해야 하므로
반드시 메인 프로그램으로 직접 실행해야 한다 (import 시 종료).
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
from io_board import __version__
from services.polling import data_sources, polling_service
from services.io_board.sanitizer import configure_sanitizer
from services.io_board.serial_io import configure_serial

logger = get_logger(__name__)

# streaming 협조적 중단을 위한 공유 shutdown 신호
stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 lifespan context manager.

    startup: serial/sanitizer/throttle 설정, polling·recording·
    error state management 서비스 시작.
    shutdown: 역순으로 서비스 정지.
    """

    app.state.stop_event = stop_event

    settings = app.state.settings

    setup_logging(settings.api.log_level.upper())

    configure_serial(settings.serial)
    configure_sanitizer(settings.sanitize)

    import services.io_board.commands as commands
    commands.configure_loadcell_throttle(settings.polling.loadcells_min_request_gap)

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
        door_open_error_seconds=settings.health.door_open_error_seconds,
        deadbolt_apply_timeout_seconds=settings.health.deadbolt_apply_timeout_seconds,
    )

    app.state.recording_services = {
        "loadcells": loadcells_recording_service,
        "error_state_management": error_state_management_service,
    }

    # polling 서비스 시작
    await loadcells_polling_service.start()
    await io_status_polling_service.start()

    # recording 서비스 시작
    await loadcells_recording_service.start()
    await error_state_management_service.start()
    try:
        yield
    finally:
        # recording 서비스 정지
        await loadcells_recording_service.stop()
        await error_state_management_service.stop()
        # polling 서비스 정지
        await loadcells_polling_service.stop()
        await io_status_polling_service.stop()
        logger.info("IO Board Control Service Stopped")


app = FastAPI(
    title="IO Board Control API",
    description="REST API for controlling IO Board device with loadcells, door locks, and sensors",
    # 버전 단일 소스: io_board.__version__ (CHANGELOG.md 최신 버전과 일치)
    version=__version__,
    lifespan=lifespan,
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """correlation ID가 포함된 request/response 로깅 middleware.

    모든 요청/응답을 소요 시간과 함께 로깅하고, 요청 추적을 위한
    correlation ID를 응답 헤더에 추가한다.
    """
    # 이 요청의 correlation ID 생성
    correlation_id = set_correlation_id()

    # 수신 요청 로깅
    logger.info(
        f"Request started: method={request.method} path={request.url.path} "
        f"client={request.client.host if request.client else 'unknown'}"
    )

    # POST/PUT/PATCH의 request body 로깅
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.body()
            if body:
                logger.debug(f"Request body: {body.decode('utf-8')}")
        except Exception:
            pass

    # 요청 처리 및 소요 시간 측정
    try:
        with PerformanceLogger(logger, "request", path=request.url.path):
            response = await call_next(request)

        # 응답 로깅
        logger.info(f"Request completed: status={response.status_code}")

        # 응답 헤더에 correlation ID 추가
        response.headers["X-Correlation-ID"] = correlation_id

        return response
    finally:
        clear_correlation_id()


@app.exception_handler(IOBoardError)
async def ioboard_error_handler(request: Request, exc: IOBoardError) -> JSONResponse:
    """IO Board 에러 전역 exception handler.

    모든 IOBoardError 예외를 표준 JSON 에러 응답으로 변환한다.
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
    """Pydantic 검증 에러 전역 exception handler.

    검증 에러를 표준 JSON 에러 응답으로 변환한다.
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
    """예기치 못한 에러의 전역 exception handler.

    전체 예외를 로깅하고, 내부 세부사항을 노출하지 않는 일반 에러
    응답을 반환한다.
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
    """graceful shutdown을 처리하는 uvicorn Server 서브클래스."""

    async def shutdown(self, *args, **kwargs) -> None:
        """stop event를 설정해 SSE 등 streaming 소비자에게 종료를 알린다."""
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
    # graceful shutdown을 위해 uvicorn Server 구현 교체가 필수이므로
    # 이 모듈이 import되면 에러로 종료한다
    print("This module is intended to be run as the main program.")
    exit(1)
