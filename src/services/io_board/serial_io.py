"""IO Board serial 통신 layer.

IO Board 디바이스와의 비동기 serial 통신을 제공한다.
exponential backoff retry, 구조화된 로깅, 에러 분류를 포함하며,
mutex로 serial 포트 접근을 직렬화한다. 연결은 요청마다 열지 않고
재사용한다 (연결 유지 방식).
"""

import asyncio
import os
from typing import Optional

import serial
import serial_asyncio

from core.config import SerialModel
from core.logging_config import PerformanceLogger, get_logger, log_payload
from exceptions import ErrorCode, SerialCommunicationError

logger = get_logger(__name__)

# 전역 serial 설정과 mutex (포트 접근 직렬화)
_serial_config: Optional[SerialModel] = None
_serial_mutex = asyncio.Lock()


def configure_serial(config: SerialModel) -> None:
    """serial 통신 파라미터를 설정한다. startup 시 1회 호출.

    Args:
        config: serial 설정 객체
    """
    global _serial_config
    _serial_config = config
    logger.info(
        f"Serial configured: port={config.port} baudrate={config.baudrate} "
        f"timeouts=({config.header_timeout}s/{config.body_timeout}s/{config.checksum_timeout}s) "
        f"retries={config.max_retries}"
    )


def get_serial_config() -> SerialModel:
    """현재 serial 설정을 반환한다.

    Returns:
        serial 설정 객체

    Raises:
        SerialCommunicationError: serial이 아직 설정되지 않은 경우
    """
    if _serial_config is None:
        raise SerialCommunicationError(
            "Serial communication not configured",
            ErrorCode.SERIAL_CONNECTION_FAILED,
            {"reason": "configure_serial() must be called before use"}
        )
    return _serial_config

# 재사용되는 전역 serial 연결 (요청마다 열지 않음)
reader: Optional[asyncio.StreamReader] = None
writer: Optional[asyncio.StreamWriter] = None

async def get_serial_connection():
    """현재 설정으로 비동기 serial 연결을 가져온다 (기존 연결 재사용).

    Returns:
        serial 연결의 (StreamReader, StreamWriter) 튜플

    Raises:
        SerialCommunicationError: serial 미설정 또는 연결 실패 시
    """
    global reader, writer

    # 살아있는 기존 연결이 있으면 그대로 재사용
    if reader is not None and writer is not None and not writer.is_closing():
        return reader, writer

    # 닫히는 중인 기존 연결이 있으면 완전히 닫힐 때까지 대기
    if writer is not None:
        logger.debug("Waiting for existing serial connection to close")
        writer.close()
        await writer.wait_closed()
        reader = None
        writer = None

    # 새 serial 연결 수립
    config = get_serial_config()
    logger.info(f"Opening serial port: {config.port} @ {config.baudrate} baud")
    try:
        reader, writer = await serial_asyncio.open_serial_connection(
            url=config.port,
            baudrate=config.baudrate,
        )

        # POSIX 시스템에서 지원되면 low latency 모드 활성화
        if os.name == 'posix':
            try:
                serial_instance: serial.Serial = writer.transport.get_extra_info('serial')
                serial_instance.set_low_latency_mode(True)
            except NotImplementedError:
                logger.warning("Low latency mode not supported on this platform/driver")

        return reader, writer
    except serial.SerialException as e:
        error_msg = str(e).lower()

        # serial 에러를 원인별 에러 코드로 분류
        if "access is denied" in error_msg or "permission" in error_msg:
            raise SerialCommunicationError(
                f"Permission denied accessing serial port",
                ErrorCode.SERIAL_PORT_PERMISSION_DENIED,
                {"port": config.port}
            ) from e
        elif "cannot find" in error_msg or "does not exist" in error_msg:
            raise SerialCommunicationError(
                f"Serial port not found",
                ErrorCode.SERIAL_PORT_NOT_FOUND,
                {"port": config.port}
            ) from e
        elif "busy" in error_msg or "in use" in error_msg:
            raise SerialCommunicationError(
                f"Serial port busy or already in use",
                ErrorCode.SERIAL_PORT_BUSY,
                {"port": config.port}
            ) from e
        else:
            raise SerialCommunicationError(
                f"Failed to open serial port",
                ErrorCode.SERIAL_CONNECTION_FAILED,
                {"port": config.port, "error": str(e)}
            ) from e


async def _drain_stale_input(reader: asyncio.StreamReader) -> None:
    """수신 buffer에 남아있는 오래된(orphaned) 바이트를 모두 버린다.

    이전 교환에서 지연 도착한 응답 조각이 buffer에 남아있으면 이번에 보낼
    요청의 응답과 뒤섞여 CMD/SUBCMD mismatch를 유발할 수 있다 (여러
    polling 서비스가 하나의 serial 연결을 공유하므로, 한 교환이 timeout
    등으로 어긋나면 그 응답이 다음 무관한 요청의 응답인 것처럼 읽힐 수
    있음). 새 요청을 보내기 전에 아주 짧은 timeout으로 반복 읽어 남은
    바이트를 모두 버린다.

    Args:
        reader: serial 포트의 비동기 stream reader
    """
    drained = b""
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=0.05)
        except asyncio.TimeoutError:
            break
        if not chunk:
            break
        drained += chunk
    if drained:
        logger.warning(
            f"Discarded {len(drained)} stale byte(s) from serial input buffer "
            f"before sending request: {drained.hex()}"
        )


async def _fetch_with_timeout(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    message: bytes
) -> bytes:
    """메시지를 전송하고 단계별 timeout을 적용해 응답을 수신한다.

    protocol frame의 각 단계(STX/본문/checksum)에 개별 timeout을
    적용하는 저수준 serial I/O 내부 함수.

    Args:
        reader: serial 포트의 비동기 stream reader
        writer: serial 포트의 비동기 stream writer
        message: 전송할 바이너리 메시지

    Returns:
        완전한 바이너리 응답 메시지

    Raises:
        asyncio.TimeoutError: 읽기 단계 중 하나라도 timeout된 경우
        asyncio.IncompleteReadError: 응답 완료 전에 연결이 닫힌 경우
    """
    config = get_serial_config()

    # request 메시지 전송
    log_payload(logger, "TX", message, "request")
    writer.write(message)
    await writer.drain()

    # 응답 frame을 세 단계로 나눠 각각의 timeout으로 읽는다
    response = b""

    # 1단계: STX (Start of Text) 바이트 읽기
    response += await asyncio.wait_for(
        reader.readexactly(1),
        timeout=config.header_timeout
    )

    # 2단계: ETX (End of Text) 바이트까지 읽기
    response += await asyncio.wait_for(
        reader.readuntil(b"\x03"),
        timeout=config.body_timeout
    )

    # 3단계: checksum 바이트 읽기
    response += await asyncio.wait_for(
        reader.readexactly(1),
        timeout=config.checksum_timeout
    )

    log_payload(logger, "RX", response, "response")
    return response


async def fetch(message: bytes) -> bytes:
    """IO Board에 메시지를 전송하고 retry 로직과 함께 응답을 수신한다.

    다음을 포함한 안전한 serial 통신을 구현한다:
    - mutex 기반 배타적 포트 접근
    - exponential backoff retry 전략
    - 에러 분류 및 구조화된 로깅
    - 자동 연결 관리 (연결 재사용, 에러 시 reset)

    Args:
        message: 전송할 바이너리 protocol 메시지

    Returns:
        디바이스의 바이너리 protocol 응답

    Raises:
        SerialCommunicationError: 모든 retry 후에도 통신이 실패한 경우
    """
    config = get_serial_config()

    async with _serial_mutex:
        with PerformanceLogger(logger, "serial_fetch", port=config.port):
            reader, writer = await get_serial_connection()

            try:
                # 이전 교환에서 남은 orphaned 바이트가 이번 응답과 뒤섞이지
                # 않도록, 요청을 보내기 전에 buffer를 비운다
                await _drain_stale_input(reader)

                # exponential backoff retry 루프
                retry_delay = config.initial_retry_delay
                last_exception: Optional[Exception] = None

                for attempt in range(1, config.max_retries + 1):
                    try:
                        logger.debug(f"Attempt {attempt}/{config.max_retries}")
                        response = await _fetch_with_timeout(reader, writer, message)
                        logger.debug(f"Fetch successful on attempt {attempt}")
                        return response
                        
                    except asyncio.TimeoutError as e:
                        last_exception = e
                        logger.warning(
                            f"Timeout on attempt {attempt}/{config.max_retries} "
                            f"(will retry in {retry_delay:.3f}s)"
                        )

                        if attempt < config.max_retries:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= config.retry_backoff_multiplier
                            # timeout된 요청의 응답이 뒤늦게 도착해 다음
                            # 재전송의 응답과 뒤섞이지 않도록 재전송 전에도 비운다
                            await _drain_stale_input(reader)

                    except asyncio.IncompleteReadError as e:
                        last_exception = e
                        logger.warning(
                            f"Incomplete read on attempt {attempt}/{config.max_retries}: "
                            f"expected={e.expected} received={len(e.partial)} "
                            f"(will retry in {retry_delay:.3f}s)"
                        )

                        if attempt < config.max_retries:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= config.retry_backoff_multiplier
                            await _drain_stale_input(reader)
                
                # 모든 retry 소진
                if isinstance(last_exception, asyncio.TimeoutError):
                    raise SerialCommunicationError(
                        f"Serial read timeout after {config.max_retries} attempts",
                        ErrorCode.SERIAL_TIMEOUT,
                        {
                            "port": config.port,
                            "attempts": config.max_retries,
                            "message_hex": message.hex()
                        }
                    ) from last_exception
                else:
                    raise SerialCommunicationError(
                        f"Incomplete serial read after {config.max_retries} attempts",
                        ErrorCode.SERIAL_INCOMPLETE_READ,
                        {
                            "port": config.port,
                            "attempts": config.max_retries,
                            "message_hex": message.hex()
                        }
                    ) from last_exception
            
            except Exception as e:
                # 예기치 못한 에러 시 연결을 reset한다. 정상 경로에서는
                # 연결을 닫지 않고 다음 요청에서 재사용한다.
                logger.error(f"Serial communication error: {e} (resetting connection)")
                writer.close()
                await writer.wait_closed()
                raise