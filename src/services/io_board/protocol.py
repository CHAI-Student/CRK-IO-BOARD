"""
IO Board binary protocol implementation.

This module implements the binary communication protocol for the IO Board device
using the Construct library for declarative binary parsing and building.

Protocol Frame Structure:
    [STX 0x02][CMD 2B][SUBCMD 2B][DATA VAR][ETX 0x03][CHECKSUM 1B]

Checksum Calculation:
    XOR of all bytes between STX (exclusive) and ETX (exclusive)
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
    """
    Read data from stream at specified offset without changing position.
    
    This helper function is used by the Checksum construct to read the data
    range that needs to be checksummed without affecting the current stream position.
    
    Args:
        stream: Byte stream to read from
        offset: Byte offset to start reading
        length: Number of bytes to read
        
    Returns:
        Bytes read from the specified range
    """
    org_pos = stream.tell()
    stream.seek(offset)
    data = stream.read(length)
    stream.seek(org_pos)
    return data


def calculate_checksum(data: bytes) -> int:
    """
    Calculate XOR checksum for protocol message.
    
    The checksum is calculated by XORing all bytes in the data.
    
    Args:
        data: Bytes to calculate checksum for
        
    Returns:
        Single-byte XOR checksum value (0-255)
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
                "DEADBOLT" / Enum(Byte, OPENED=ord("O"), LOCKED=ord("C")),
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
    """
    Build a protocol request message.
    
    Args:
        command: Command code (2 characters, e.g., "MC", "RQ")
        subcommand: Subcommand code (2 characters, e.g., "PD", "MI")
        data: Command-specific data dictionary
        
    Returns:
        Binary protocol message ready for transmission
        
    Raises:
        ProtocolError: If message building fails
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
    """
    Parse a protocol response message.
    
    Args:
        message: Binary protocol message received from device
        
    Returns:
        Parsed response structure with COMMAND, SUBCOMMAND, and DATA fields
        
    Raises:
        ProtocolError: If message parsing fails or checksum is invalid
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
        
        # Provide more specific error messages
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

