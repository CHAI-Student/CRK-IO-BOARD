"""IO Board serial 통신 layer.

IO Board 디바이스와의 비동기 serial 통신을 제공한다.
exponential backoff retry, 구조화된 로깅, 에러 분류를 포함하며,
mutex로 serial 포트 접근을 직렬화한다. 연결은 요청마다 열지 않고
재사용한다 (연결 유지 방식).
"""

import asyncio
import os
from dataclasses import dataclass
from functools import reduce
from typing import Optional

import serial
import serial_asyncio

from core.config import SerialModel
from core.logging_config import PerformanceLogger, get_logger, log_payload
from exceptions import ErrorCode, ProtocolError, SerialCommunicationError

logger = get_logger(__name__)

# 전역 serial 설정과 mutex (포트 접근 직렬화)
_serial_config: Optional[SerialModel] = None
_serial_mutex = asyncio.Lock()
# 실제 wire 전송 시각. 상위 API 호출 throttle만으로는 fetch() 내부 timeout
# 재전송까지 제한할 수 없으므로 request 종류별 마지막 TX를 여기서
# 추적한다.
_last_request_tx: dict[bytes, float] = {}


@dataclass(frozen=True)
class _WireTx:
    """Mismatch 진단에 필요한 직전 wire TX 메타데이터."""

    transaction_id: int
    attempt: int
    command: str
    subcommand: str
    timestamp: float


_transaction_sequence = 0
_last_wire_tx: _WireTx | None = None
# 마지막 완전한 frame(checksum 포함)을 읽은 monotonic 시각. 명령 종류와
# 호출 경로에 관계없이 firmware에 실제 정숙 시간을 보장하는 데 사용한다.
_last_rx_complete_time: float | None = None

# protocol.py의 response schema와 동일한 전체 frame 길이
# (STX + CMD/SUBCMD + DATA + ETX + LRC). mismatch frame은 정식 parser에
# 넘기기 전에 폐기되므로 여기서 shape만 진단하기 위한 읽기 전용 표다.
_RESPONSE_FRAME_LENGTHS: dict[tuple[str, str], int] = {
    ("MC", "PD"): 7,
    ("MC", "DC"): 8,
    ("MC", "LZ"): 7,
    ("MC", "WP"): 18,
    ("MC", "EZ"): 7,
    ("MC", "RT"): 7,
    ("RQ", "MI"): 20,
    ("RQ", "IW"): 67,
    ("RQ", "ID"): 19,
    ("RQ", "ER"): 23,
}


def configure_serial(config: SerialModel) -> None:
    """serial 통신 파라미터를 설정한다. startup 시 1회 호출.

    Args:
        config: serial 설정 객체
    """
    global _serial_config, _transaction_sequence, _last_wire_tx, _last_rx_complete_time
    _serial_config = config
    _last_request_tx.clear()
    _transaction_sequence = 0
    _last_wire_tx = None
    _last_rx_complete_time = None
    logger.info(
        f"Serial configured: port={config.port} baudrate={config.baudrate} "
        f"timeouts=({config.header_timeout}s/{config.body_timeout}s/{config.checksum_timeout}s) "
        f"retries={config.max_retries} inter_command_gap={config.inter_command_gap}s"
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


def _response_codes(response: bytes) -> tuple[str, str] | None:
    """완전한 응답 frame의 CMD/SUBCMD를 가볍게 읽는다.

    checksum을 포함한 정식 검증은 상위 protocol parser가 담당한다. 여기서는
    이미 완전한 frame으로 읽은 응답이 현재 transaction의 것인지 판별해,
    mismatch 시 동일 요청을 재전송할지 결정하는 용도로만 사용한다.
    """
    if len(response) < 5 or response[0:1] != b"\x02":
        return None
    try:
        return response[1:3].decode("ascii"), response[3:5].decode("ascii")
    except UnicodeDecodeError:
        return None


def _xor_checksum(data: bytes) -> int:
    """protocol checksum 구간(CMD부터 ETX 포함)의 XOR을 계산한다."""
    return reduce(lambda left, right: left ^ right, data, 0)


def _frame_diagnostics(response: bytes) -> str:
    """정식 parser 전 mismatch frame의 무손실 진단 문자열을 만든다.

    요청 echo, 정상적인 다른 response, header/payload 혼합, checksum 손상을
    현장 로그 한 줄만으로 구분할 수 있도록 길이·shape·checksum·전체 hex를
    기록한다. 이 함수는 진단만 하며 frame의 수락 여부에는 영향을 주지 않는다.
    """
    codes = _response_codes(response)
    expected_length = _RESPONSE_FRAME_LENGTHS.get(codes) if codes else None

    if len(response) >= 3 and response[0:1] == b"\x02" and response[-2:-1] == b"\x03":
        calculated = _xor_checksum(response[1:-1])
        received = response[-1]
        checksum = (
            f"valid(0x{received:02X})"
            if calculated == received
            else f"invalid(received=0x{received:02X},calculated=0x{calculated:02X})"
        )
    else:
        checksum = "unavailable(incomplete-frame-markers)"

    if len(response) == 7:
        shape = "request-sized-or-empty-response"
    elif expected_length is None:
        shape = "unknown"
    elif len(response) == expected_length:
        shape = "known-response-size"
    else:
        shape = f"size-mismatch(expected={expected_length})"

    return (
        f"rx_len={len(response)} rx_shape={shape} rx_checksum={checksum} "
        f"rx_hex={response.hex().upper()}"
    )


def _tx_gap_diagnostics(previous: _WireTx | None, current_tx_time: float) -> str:
    """현재 TX와 직전 wire TX 사이의 종류·간격을 문자열로 반환한다."""
    if previous is None:
        return "previous_tx=none tx_gap_ms=none"
    gap_ms = (current_tx_time - previous.timestamp) * 1000
    return (
        f"previous_tx={previous.command}/{previous.subcommand} "
        f"previous_txn={previous.transaction_id} "
        f"previous_attempt={previous.attempt} tx_gap_ms={gap_ms:.3f}"
    )


async def _respect_wire_min_gap(message: bytes, min_send_interval: float) -> None:
    """동일 request의 실제 serial TX 간 최소 간격을 강제한다.

    특히 RQIW는 0.7초 미만 재전송 시 firmware가 부호를 손상시킨다. 이 함수는
    timeout retry에도 호출되므로 get_loadcells() 바깥 throttle의 사각지대를
    막는다. 호출부는 _serial_mutex를 보유하므로 별도 lock이 필요 없다.
    """
    if min_send_interval <= 0:
        return
    key = message[:5]
    previous = _last_request_tx.get(key)
    if previous is not None:
        remaining = min_send_interval - (asyncio.get_running_loop().time() - previous)
        if remaining > 0:
            logger.warning(
                f"Delaying {key[1:5].decode('ascii', errors='replace')} retry "
                f"by {remaining:.3f}s to preserve wire min gap"
            )
            await asyncio.sleep(remaining)
async def _respect_inter_command_gap(min_gap: float) -> None:
    """완전한 RX frame과 다음 wire TX 사이의 전역 최소 간격을 강제한다.

    API handler의 sleep과 달리 SSE, health, recording, retry를 포함한 모든
    호출 경로에 적용된다. 호출부는 _serial_mutex를 보유한다.
    """
    if min_gap <= 0 or _last_rx_complete_time is None:
        return
    remaining = min_gap - (
        asyncio.get_running_loop().time() - _last_rx_complete_time
    )
    if remaining > 0:
        logger.debug(
            f"Delaying next wire TX by {remaining:.3f}s to preserve "
            f"RX-to-TX inter-command gap ({min_gap:.3f}s)"
        )
        await asyncio.sleep(remaining)


def _rx_to_tx_gap_diagnostics(last_rx_time: float | None, tx_time: float) -> str:
    """현재 TX 직전 완전한 RX와의 간격을 진단 문자열로 반환한다."""
    if last_rx_time is None:
        return "rx_to_tx_gap_ms=none"
    return f"rx_to_tx_gap_ms={(tx_time - last_rx_time) * 1000:.3f}"


async def fetch(
    message: bytes,
    *,
    expected_command: str | None = None,
    expected_subcommand: str | None = None,
    min_send_interval: float = 0.0,
) -> bytes:
    """IO Board에 메시지를 전송하고 retry 로직과 함께 응답을 수신한다.

    다음을 포함한 안전한 serial 통신을 구현한다:
    - mutex 기반 배타적 포트 접근
    - exponential backoff retry 전략
    - 에러 분류 및 구조화된 로깅
    - 자동 연결 관리 (연결 재사용, 에러 시 reset)

    Args:
        message: 전송할 바이너리 protocol 메시지
        expected_command: 기대 response CMD. subcommand와 함께 주어지면 다른
            응답을 폐기하고 exponential backoff 후 동일 요청을 재전송한다.
        expected_subcommand: 기대 response SUBCMD.
        min_send_interval: 동일 request의 실제 TX 간 최소 간격. 내부 retry에도
            적용된다.

    Returns:
        디바이스의 바이너리 protocol 응답

    Raises:
        SerialCommunicationError: 모든 retry 후에도 통신이 실패한 경우
    """
    global _transaction_sequence, _last_wire_tx, _last_rx_complete_time

    config = get_serial_config()

    async with _serial_mutex:
        _transaction_sequence += 1
        transaction_id = _transaction_sequence
        with PerformanceLogger(logger, "serial_fetch", port=config.port):
            reader, writer = await get_serial_connection()

            try:
                # exponential backoff retry 루프
                retry_delay = config.initial_retry_delay
                last_exception: Optional[Exception] = None
                discarded_total = 0

                for attempt in range(1, config.max_retries + 1):
                    unexpected = 0
                    tx_time: float | None = None
                    previous_tx: _WireTx | None = None
                    previous_rx_time: float | None = None
                    try:
                        logger.debug(
                            f"Transaction {transaction_id} attempt "
                            f"{attempt}/{config.max_retries}"
                        )
                        await _respect_inter_command_gap(config.inter_command_gap)
                        await _respect_wire_min_gap(message, min_send_interval)

                        # 모든 timing wait가 끝난 뒤,
                        # 실제 TX 직전에 늦게 도착한 stale response를 제거
                        await _drain_stale_input(reader)

                        tx_time = asyncio.get_running_loop().time()
                        previous_tx = _last_wire_tx
                        previous_rx_time = _last_rx_complete_time
                        _last_request_tx[message[:5]] = tx_time
                        tx_codes = _response_codes(message)
                        tx_command = tx_codes[0] if tx_codes else "??"
                        tx_subcommand = tx_codes[1] if tx_codes else "??"
                        _last_wire_tx = _WireTx(
                            transaction_id=transaction_id,
                            attempt=attempt,
                            command=tx_command,
                            subcommand=tx_subcommand,
                            timestamp=tx_time,
                        )
                        response = await _fetch_with_timeout(reader, writer, message)
                        _last_rx_complete_time = asyncio.get_running_loop().time()

                        # 다른 logical command의 응답이면 폐기하고 같은 serial
                        # ownership을 유지한 채 동일 요청을 재전송한다.
                        if expected_command is not None and expected_subcommand is not None:
                            expected = (expected_command, expected_subcommand)
                            codes = _response_codes(response)
                            if codes != expected:
                                unexpected += 1
                                discarded_total += 1

                                got = (
                                    f"{codes[0]}/{codes[1]}"
                                    if codes is not None
                                    else "unreadable header"
                                )
                                rx_after_tx_ms = (
                                    (asyncio.get_running_loop().time() - tx_time) * 1000
                                    if tx_time is not None
                                    else float("nan")
                                )
                                logger.warning(
                                    "Unexpected response CMD/SUBCMD: "
                                    f"txn={transaction_id} "
                                    f"attempt={attempt}/{config.max_retries} "
                                    f"expected={expected_command}/{expected_subcommand} "
                                    f"got={got} "
                                    f"rx_after_tx_ms={rx_after_tx_ms:.3f} "
                                    f"{_tx_gap_diagnostics(previous_tx, tx_time)} "
                                    f"{_rx_to_tx_gap_diagnostics(previous_rx_time, tx_time)} "
                                    f"{_frame_diagnostics(response)}. "
                                    "Discarding mismatched response and retrying same request..."
                                )

                                if attempt < config.max_retries:
                                    await asyncio.sleep(retry_delay)
                                    retry_delay *= config.retry_backoff_multiplier
                                    continue

                                raise ProtocolError(
                                    "Response CMD/SUBCMD mismatch after "
                                    f"{config.max_retries} attempts",
                                    ErrorCode.PROTOCOL_INVALID_RESPONSE,
                                    {
                                        "command": expected_command,
                                        "subcommand": expected_subcommand,
                                        "last_received": got,
                                        "attempts": config.max_retries,
                                    },
                                )

                        if discarded_total:
                            rx_after_tx_ms = (
                                (asyncio.get_running_loop().time() - tx_time) * 1000
                                if tx_time is not None
                                else float("nan")
                            )
                            logger.warning(
                                "Serial transaction recovered: "
                                f"txn={transaction_id} attempt={attempt}/{config.max_retries} "
                                f"expected={expected_command}/{expected_subcommand} "
                                f"discarded_total={discarded_total} "
                                f"rx_after_tx_ms={rx_after_tx_ms:.3f} "
                                f"{_frame_diagnostics(response)}"
                            )
                        logger.debug(f"Fetch successful on attempt {attempt}")
                        return response

                    except asyncio.TimeoutError as e:
                        last_exception = e
                        elapsed_ms = (
                            (asyncio.get_running_loop().time() - tx_time) * 1000
                            if tx_time is not None
                            else float("nan")
                        )
                        logger.warning(
                            "Serial response timeout: "
                            f"txn={transaction_id} attempt={attempt}/{config.max_retries} "
                            f"expected={expected_command}/{expected_subcommand} "
                            f"elapsed_after_tx_ms={elapsed_ms:.3f} "
                            f"discarded_on_attempt={unexpected} "
                            f"retry_delay_s={retry_delay:.3f}"
                        )

                        if attempt < config.max_retries:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= config.retry_backoff_multiplier

                    except asyncio.IncompleteReadError as e:
                        last_exception = e
                        elapsed_ms = (
                            (asyncio.get_running_loop().time() - tx_time) * 1000
                            if tx_time is not None
                            else float("nan")
                        )
                        logger.warning(
                            "Incomplete serial read: "
                            f"txn={transaction_id} attempt={attempt}/{config.max_retries} "
                            f"expected={expected_command}/{expected_subcommand} "
                            f"bytes_expected={e.expected} bytes_received={len(e.partial)} "
                            f"partial_hex={e.partial.hex().upper()} "
                            f"elapsed_after_tx_ms={elapsed_ms:.3f} "
                            f"retry_delay_s={retry_delay:.3f}"
                        )

                        if attempt < config.max_retries:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= config.retry_backoff_multiplier

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
