"""IO Board 고수준 command 인터페이스.

저수준 protocol 세부사항과 분리된 비즈니스 로직 layer.
initialize/calibrate/deadbolt 제어 같은 management command와
loadcell·IO status 조회 같은 request command를 제공하며,
loadcell 조회에는 전역 request throttle(부호 손상 방지)과
sanitizer(sign-glitch 보정)가 적용된다.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from exceptions import DeviceError, ErrorCode, ProtocolError, ValidationError
from core.logging_config import PerformanceLogger, get_logger
from services.io_board.protocol import build_request, parse_response
from services.io_board.sanitizer import sanitize_loadcells
from services.io_board.serial_io import fetch
from services.io_board.io_types import (
    CommandType,
    DeadboltAction,
    DeadboltState,
    DoorState,
    ManagementSubcommand,
    ProductInfoData,
    RequestSubcommand,
    IOStatusData,
)

logger = get_logger(__name__)


async def _send_command(
    command: CommandType,
    subcommand: RequestSubcommand | ManagementSubcommand,
    data: Dict[str, Any]
) -> Any:
    """IO Board에 command를 전송하고 파싱된 응답을 반환한다.

    protocol 빌드, serial 송수신, 응답 파싱을 묶은 내부 helper.
    응답 matching과 재시도는 하나의 serial transaction 소유권 안에서
    수행된다.

    Args:
        command: command 종류 (MC 또는 RQ)
        subcommand: 세부 subcommand 코드
        data: command별 데이터 payload

    Returns:
        파싱된 응답 구조체

    Raises:
        ValidationError: command/subcommand 타입이 불일치할 때
        ProtocolError: protocol 빌드/파싱 실패 또는 관련 없는 응답이
            반복되어 요청에 해당하는 응답을 얻지 못한 경우
        SerialCommunicationError: serial 통신 실패 시
    """

    if command == CommandType.MANAGEMENT_CONTROL and not isinstance(subcommand, ManagementSubcommand):
        raise ValidationError("Mismatched subcommand type for MANAGEMENT_CONTROL command")
    if command == CommandType.REQUEST and not isinstance(subcommand, RequestSubcommand):
        raise ValidationError("Mismatched subcommand type for REQUEST command")

    with PerformanceLogger(logger, "command", cmd=f"{command.value}/{subcommand.value}"):
        # Build request message
        request_message = build_request(command.value, subcommand.value, data)
        # response matching과 재시도는 하나의 serial ownership 안에서
        # 수행한다. mismatch 시 동일 요청을 재전송하되 다른 command가 중간에
        # 끼어들지 못한다. RQIW에는 실제 wire 재전송까지 min gap을 적용해
        # firmware sign 손상을 방지한다.
        response_message = await fetch(
            request_message,
            expected_command=command.value,
            expected_subcommand=subcommand.value,
            min_send_interval=(
                _loadcell_min_gap
                if command == CommandType.REQUEST
                and subcommand == RequestSubcommand.LOADCELL_WEIGHTS
                else 0.0
            ),
        )

        response = parse_response(response_message)
        if response.COMMAND != command.value or response.SUBCOMMAND != subcommand.value:
            # fetch()가 header 기준으로 일치시킨 뒤의 방어적 검증이다.
            raise ProtocolError(
                "Parsed response CMD/SUBCMD did not match request",
                ErrorCode.PROTOCOL_INVALID_RESPONSE,
                {
                    "expected": f"{command.value}/{subcommand.value}",
                    "received": f"{response.COMMAND}/{response.SUBCOMMAND}",
                },
            )
        return response


@asynccontextmanager
async def _session(command: str, **kwargs) -> AsyncIterator[None]:
    """DeviceError를 command 컨텍스트가 포함된 에러로 감싸는 helper."""
    try:
        yield
    except DeviceError as e:
        raise DeviceError(
            f"Command '{command}' failed",
            ErrorCode.DEVICE_COMMAND_FAILED,
            {'command': command} | kwargs
        ) from e


async def initialize() -> None:
    """IO Board 디바이스를 초기화한다.

    디바이스 전원 인가 또는 reset 후 1회 호출해 모든 서브시스템을
    초기화한다.

    Raises:
        DeviceError: 초기화 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('initialize'):
        logger.info("Initializing IO Board")
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.INITIALIZE,
            {}
        )
        logger.info("IO Board initialized")


async def set_deadbolt(action: DeadboltAction) -> DeadboltState:
    """deadbolt(도어락)를 제어한다.

    Args:
        action: 원하는 deadbolt 동작 (OPEN 또는 CLOSE)

    Returns:
        command 실행 후 디바이스가 보고한 실제 deadbolt 상태

    Raises:
        DeviceError: deadbolt 제어 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('set_deadbolt', action=action.value):
        logger.info(f"Setting deadbolt: {action.value}")
        response = await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.DEADBOLT_CONTROL,
            {"DEADBOLT": action.value}
        )
        state = DeadboltState(response.DATA.DEADBOLT)
        logger.info(f"Deadbolt set: {state.value}")
        return state


async def calibrate() -> None:
    """IO Board 센서(loadcell)를 calibrate한다.

    모든 무게 센서에 대한 calibration 시퀀스를 시작한다.
    calibration 전에 디바이스는 무부하 상태여야 한다.

    Raises:
        DeviceError: calibration 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('calibrate'):
        logger.info("Calibrating loadcells")
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.CALIBRATE,
            {}
        )
        logger.info("Loadcells calibrated")


async def set_manufacturing_number(manufacturing_number: str) -> str:
    """디바이스 제조번호(product ID)를 설정한다.

    Args:
        manufacturing_number: 11자리 영숫자 product ID

    Returns:
        디바이스가 확인(echo back)한 제조번호

    Raises:
        DeviceError: 제조번호 설정 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
        ValidationError: 제조번호 형식이 잘못된 경우
    """
    async with _session('set_manufacturing_number', manufacturing_number=manufacturing_number):
        logger.info(f"Setting manufacturing number: {manufacturing_number}")
        response = await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.WRITE_PRODUCT_ID,
            {"PRODUCT_ID": manufacturing_number}
        )
        manufacturing_number = response.DATA.PRODUCT_ID
        logger.info(f"Manufacturing number set: {manufacturing_number}")
        return manufacturing_number


async def clear_errors() -> None:
    """디바이스 에러 로그를 비운다.

    디바이스 에러 히스토리에 저장된 모든 에러 코드를 삭제한다.

    Raises:
        DeviceError: 에러 삭제 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('clear_errors'):
        logger.info("Clearing error logs")
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.CLEAR_ERRORS,
            {}
        )
        logger.info("Error logs cleared")


async def reboot() -> None:
    """IO Board 디바이스를 재부팅한다.

    디바이스 재시작을 시작하며, 재부팅 동안 몇 초간 디바이스를 사용할 수
    없다.

    Raises:
        DeviceError: reboot command 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('reboot'):
        logger.info("Sending reboot command")
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.REBOOT,
            {}
        )
        logger.info("Reboot command sent")


async def get_product_info() -> ProductInfoData:
    """디바이스 제조 정보를 조회한다.

    Returns:
        'product_id'(11자)와 'sw_version'(2자)을 담은 딕셔너리

    Raises:
        DeviceError: 제조 정보 조회 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('get_product_info'):
        logger.info("Getting product info")
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.MANUFACTURING_INFO,
            {}
        )
        result = ProductInfoData(
            product_id=response.DATA.PRODUCT_ID,
            sw_version=response.DATA.SW_VERSION
        )
        logger.info(f"Retrieved product info: {result}")
        return result


# loadcell request throttle. RQIW 요청 간격이 ~0.7s보다 촘촘하면 펌웨어가
# 부호가 손상된 값을 보고한다 (음수 참값 기준 실측 sign duty:
# 0.09s->0.89, 0.5s->0.25, 0.6s->0.03, 0.7s->0.00 —
# docs/FIRMWARE_SIGN_GLITCH_REQUEST.md 참고). 모든 소비자(HTTP, polling
# service, health check)가 하나의 gate를 공유하며, 최소 gap 이전에
# 도착한 요청은 캐시된 frame으로 응답한다.
_loadcell_min_gap: float = 0.0
_loadcell_cache: Optional[List[str]] = None
_loadcell_cache_ts: float = 0.0
_loadcell_gate = asyncio.Lock()


def configure_loadcell_throttle(min_gap: float) -> None:
    """loadcell request throttle을 설정한다. startup 시 1회 호출."""
    global _loadcell_min_gap, _loadcell_cache, _loadcell_cache_ts
    _loadcell_min_gap = min_gap
    _loadcell_cache = None
    _loadcell_cache_ts = 0.0
    logger.info(
        f"Loadcell throttle {'enabled: min gap %.2fs' % min_gap if min_gap > 0 else 'disabled'}"
    )


async def get_loadcells() -> List[str]:
    """현재 loadcell 무게 판독값을 조회한다.

    serial 요청은 설정된 최소 gap당 1회로 전역 throttle되며,
    그보다 빠른 호출은 캐시된 (sanitize된) frame을 반환한다.

    Returns:
        loadcell 판독값 10개 리스트 (각 6자).
        형식: 정상 판독값은 "+XXXXX" 또는 "-XXXXX",
              에러는 "EEEEEE", 무효값은 "VVVVVV"

    Raises:
        DeviceError: loadcell 데이터 조회 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    global _loadcell_cache, _loadcell_cache_ts
    async with _loadcell_gate:
        if (
            _loadcell_min_gap > 0
            and _loadcell_cache is not None
            and time.monotonic() - _loadcell_cache_ts < _loadcell_min_gap
        ):
            logger.debug("Loadcell values served from throttle cache")
            return list(_loadcell_cache)

        async with _session('get_loadcells'):
            logger.debug("Getting loadcell values")
            response = await _send_command(
                CommandType.REQUEST,
                RequestSubcommand.LOADCELL_WEIGHTS,
                {}
            )
            result = sanitize_loadcells(list(response.DATA.LOADCELLS))
            _loadcell_cache = list(result)
            _loadcell_cache_ts = time.monotonic()
            logger.debug(f"Loadcell values retrieved: {result}")
            return result


async def get_status() -> IOStatusData:
    """door 및 deadbolt 센서 상태를 조회한다.

    Returns:
        'door'와 'deadbolt' 상태값을 담은 IOStatusData

    Raises:
        DeviceError: IO status 조회 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('get_status'):
        logger.debug("Getting status")
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.IO_STATUS,
            {}
        )
        result = IOStatusData(
            door=DoorState(response.DATA.DOOR),
            deadbolt=DeadboltState(response.DATA.DEADBOLT)
        )
        logger.debug(f"Status retrieved: {result}")
        return result


async def get_errors() -> List[str]:
    """디바이스 에러 히스토리를 조회한다.

    Returns:
        최대 4개의 에러 코드 리스트 (각 4자).
        "0000"은 해당 슬롯에 에러가 없음을 의미한다.

    Raises:
        DeviceError: 에러 리스트 조회 실패 시
        ProtocolError: protocol 통신 실패 시
        SerialCommunicationError: serial 통신 실패 시
    """
    async with _session('get_errors'):
        logger.debug("Getting errors")
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.ERROR_LIST,
            {}
        )
        result = list(response.DATA.ERRORS)
        logger.debug(f"Errors retrieved: {result}")
        return result
