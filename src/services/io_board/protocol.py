"""IO Board 바이너리 protocol 구현.

Construct 라이브러리의 선언적 바이너리 파싱/빌드를 이용해
IO Board 디바이스와의 통신 protocol을 구현한다.

Protocol frame 구조:
    [STX 0x02][CMD 2B][SUBCMD 2B][DATA 가변][ETX 0x03][CHECKSUM 1B]

Checksum 계산:
    STX 다음 바이트부터 ETX까지(ETX 포함)의 모든 바이트 XOR
"""

from functools import reduce
from typing import Any, Dict, IO

from construct import (
    Array,
    Byte,
    Checksum,
    Const,
    ConstructError,
    Enum,
    Error,
    PaddedString,
    Pass,
    Struct,
    Switch,
    Tell,
)

from exceptions import ErrorCode, ProtocolError
from core.logging_config import get_logger

logger = get_logger(__name__)

# Protocol constants
STX = b"\x02"  # Start of Text
ETX = b"\x03"  # End of Text


def seek_and_read(stream: IO[bytes], offset: int, length: int) -> bytes:
    """스트림 위치를 바꾸지 않고 지정 offset에서 데이터를 읽는다.

    Checksum construct가 현재 스트림 위치에 영향을 주지 않으면서
    checksum 대상 구간을 읽을 때 사용하는 helper.

    Args:
        stream: 읽을 바이트 스트림
        offset: 읽기 시작 offset
        length: 읽을 바이트 수

    Returns:
        지정 구간에서 읽은 바이트
    """
    org_pos = stream.tell()
    stream.seek(offset)
    data = stream.read(length)
    stream.seek(org_pos)
    return data


def calculate_checksum(data: bytes) -> int:
    """protocol 메시지의 XOR checksum을 계산한다.

    Args:
        data: checksum을 계산할 바이트

    Returns:
        1바이트 XOR checksum 값 (0-255)
    """
    return reduce(lambda x, y: x ^ y, data, 0)


# Protocol structure definitions

RequestProtocol = Struct(
    Const(STX),  # Start of Text
    "COMMAND" / PaddedString(2, "ascii"),  # Command Code (2 ASCII chars)
    "SUBCOMMAND" / PaddedString(2, "ascii"),  # Subcommand Code (2 ASCII chars)
    "DATA" / Switch(
        lambda ctx: ctx.COMMAND + ctx.SUBCOMMAND,
        {
            # Management Control commands
            "MCPD": Pass,  # Initialize board - no data
            "MCDC": Struct(
                "DEADBOLT" / Enum(Byte, OPEN=ord("O"), CLOSE=ord("C")),
            ),  # Deadbolt control - OPEN or CLOSE
            "MCLZ": Pass,  # Calibrate - no data
            "MCWP": Struct(
                "PRODUCT_ID" / PaddedString(11, "ascii"),
            ),  # Write product ID - 11 chars
            "MCEZ": Pass,  # Clear errors - no data
            "MCRT": Pass,  # Reboot - no data
            
            # Request commands
            "RQMI": Pass,  # Manufacturing info - no data
            "RQIW": Pass,  # Loadcell weights - no data
            "RQID": Pass,  # IO status - no data
            "RQER": Pass,  # Error list - no data
        },
        default=Error,
    ),
    Const(ETX),  # End of Text
    "_length" / Tell,  # Current position for checksum calculation
    Checksum(
        Byte,
        lambda data: calculate_checksum(data),
        lambda ctx: seek_and_read(ctx._io, 1, ctx._length - 1),
    ),
)

ResponseProtocol = Struct(
    Const(STX),  # Start of Text
    "COMMAND" / PaddedString(2, "ascii"),  # Command Code (2 ASCII chars)
    "SUBCOMMAND" / PaddedString(2, "ascii"),  # Subcommand Code (2 ASCII chars)
    "DATA" / Switch(
        lambda this: this.COMMAND + this.SUBCOMMAND,
        {
            # Management Control responses
            "MCPD": Pass,  # Initialize board - no response data
            "MCDC": Struct(
                "DEADBOLT" / Enum(Byte, UNLOCK=ord("O"), LOCKED=ord("C")),
            ),  # Door control - returns state
            "MCLZ": Pass,  # Calibrate - no response data
            "MCWP": Struct(
                "PRODUCT_ID" / PaddedString(11, "ascii"),
            ),  # Write product ID - echoes back ID
            "MCEZ": Pass,  # Clear errors - no response data
            "MCRT": Pass,  # Reboot - no response data
            
            # Request responses
            "RQMI": Struct(
                "PRODUCT_ID" / PaddedString(11, "ascii"),
                "SW_VERSION" / PaddedString(2, "ascii"),
            ),  # Manufacturing info - product ID + version
            "RQIW": Struct(
                "LOADCELLS" / Array(10, PaddedString(6, "ascii")),
            ),  # Loadcell weights - 10 readings of 6 chars each
            "RQID": Struct(
                "DOOR" / PaddedString(6, "ascii"),
                "DEADBOLT" / PaddedString(6, "ascii"),
            ),  # IO status - door + deadbolt status (6 chars each)
            "RQER": Struct(
                "ERRORS" / Array(4, PaddedString(4, "ascii")),
            ),  # Error list - 4 error codes of 4 chars each
        },
    ),
    Const(ETX),  # End of Text
    "_length" / Tell,  # Current position for checksum calculation
    Checksum(
        Byte,
        lambda data: calculate_checksum(data),
        lambda ctx: seek_and_read(ctx._io, 1, ctx._length - 1),
    ),
)


def build_request(command: str, subcommand: str, data: Dict[str, Any]) -> bytes:
    """protocol request 메시지를 빌드한다.

    Args:
        command: command 코드 (2자, 예: "MC", "RQ")
        subcommand: subcommand 코드 (2자, 예: "PD", "MI")
        data: command별 데이터 딕셔너리

    Returns:
        전송 가능한 바이너리 protocol 메시지

    Raises:
        ProtocolError: 메시지 빌드 실패 시
    """
    try:
        logger.debug(f"Building request: command={command} subcommand={subcommand} data={data}")
        message = RequestProtocol.build(
            dict(COMMAND=command, SUBCOMMAND=subcommand, DATA=data)
        )
        logger.debug(f"Built request message: {message.hex()}")
        return message
    except ConstructError as e:
        raise ProtocolError(
            f"Failed to build protocol request: {command}{subcommand}",
            ErrorCode.PROTOCOL_BUILD_FAILED,
            {"command": command, "subcommand": subcommand, "error": str(e)}
        ) from e


def parse_response(message: bytes) -> Any:
    """protocol response 메시지를 파싱한다.

    Args:
        message: 디바이스에서 수신한 바이너리 protocol 메시지

    Returns:
        COMMAND, SUBCOMMAND, DATA 필드를 갖는 파싱된 응답 구조체

    Raises:
        ProtocolError: 메시지 파싱 실패 또는 checksum 불일치 시
    """
    try:
        logger.debug(f"Parsing response message: {message.hex()}")
        response = ResponseProtocol.parse(message)
        logger.debug(
            f"Parsed response: command={response.COMMAND} "
            f"subcommand={response.SUBCOMMAND} data={response.DATA}"
        )
        return response
    except ConstructError as e:
        error_msg = str(e)

        # 실패 원인별로 구체적인 에러 코드를 부여한다
        if "checksum" in error_msg.lower():
            raise ProtocolError(
                "Protocol checksum validation failed",
                ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                {"message_hex": message.hex(), "error": error_msg}
            ) from e
        elif "const" in error_msg.lower():
            raise ProtocolError(
                "Protocol frame markers invalid (missing STX/ETX)",
                ErrorCode.PROTOCOL_MALFORMED_DATA,
                {"message_hex": message.hex(), "error": error_msg}
            ) from e
        else:
            raise ProtocolError(
                "Failed to parse protocol response",
                ErrorCode.PROTOCOL_PARSE_FAILED,
                {"message_hex": message.hex(), "error": error_msg}
            ) from e

