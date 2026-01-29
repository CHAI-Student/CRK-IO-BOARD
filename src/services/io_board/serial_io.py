"""
Serial communication layer for IO Board.

This module provides async serial communication with the IO Board device,
including retry logic with exponential backoff, structured logging, and
comprehensive error handling.
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

# Global serial configuration and mutex
_serial_config: Optional[SerialModel] = None
_serial_mutex = asyncio.Lock()


def configure_serial(config: SerialModel) -> None:
    """
    Configure serial communication parameters.
    
    Args:
        config: Serial configuration object
    """
    global _serial_config
    _serial_config = config
    logger.info(
        f"Serial configured: port={config.port} baudrate={config.baudrate} "
        f"timeouts=({config.header_timeout}s/{config.body_timeout}s/{config.checksum_timeout}s) "
        f"retries={config.max_retries}"
    )


def get_serial_config() -> SerialModel:
    """
    Get current serial configuration.
    
    Returns:
        Serial configuration object
        
    Raises:
        SerialCommunicationError: If serial not configured
    """
    if _serial_config is None:
        raise SerialCommunicationError(
            "Serial communication not configured",
            ErrorCode.SERIAL_CONNECTION_FAILED,
            {"reason": "configure_serial() must be called before use"}
        )
    return _serial_config

reader: Optional[asyncio.StreamReader] = None
writer: Optional[asyncio.StreamWriter] = None

async def get_serial_connection():
    """
    Get an asynchronous serial connection using the current configuration.
    
    Returns:
        A tuple of (StreamReader, StreamWriter) for the serial connection.
        
    Raises:
        SerialCommunicationError: If serial not configured or connection fails
    """
    global reader, writer

    if reader is not None and writer is not None and not writer.is_closing():
        return reader, writer
    
    # Wait for any existing connection to close
    if writer is not None:
        logger.debug("Waiting for existing serial connection to close")
        await writer.wait_closed()
        reader = None
        writer = None

    # Establish new serial connection
    config = get_serial_config()
    logger.debug(f"Opening serial port: {config.port} @ {config.baudrate} baud")
    try:
        reader, writer = await serial_asyncio.open_serial_connection(
            url=config.port,
            baudrate=config.baudrate,
        )

        # Set low latency mode on POSIX systems if supported
        if os.name == 'posix':
            try:
                serial_instance: serial.Serial = writer.transport.get_extra_info('serial')
                serial_instance.set_low_latency_mode(True)
            except NotImplementedError:
                logger.warning("Low latency mode not supported on this platform/driver")

        return reader, writer
    except serial.SerialException as e:
        error_msg = str(e).lower()
        
        # Categorize serial errors
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


async def _fetch_with_timeout(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    message: bytes
) -> bytes:
    """
    Send message and receive response with appropriate timeouts.
    
    This internal function handles the low-level serial I/O with timeouts
    for each phase of the protocol frame.
    
    Args:
        reader: Async stream reader for serial port
        writer: Async stream writer for serial port
        message: Binary message to send
        
    Returns:
        Complete binary response message
        
    Raises:
        asyncio.TimeoutError: If any read operation times out
        asyncio.IncompleteReadError: If connection closes before response complete
    """
    config = get_serial_config()
    
    # Send request message
    log_payload(logger, "TX", message, "request")
    writer.write(message)
    await writer.drain()
    
    # Read response frame in three phases with appropriate timeouts
    response = b""
    
    # Phase 1: Read STX (Start of Text) byte
    response += await asyncio.wait_for(
        reader.readexactly(1),
        timeout=config.header_timeout
    )
    
    # Phase 2: Read until ETX (End of Text) byte
    response += await asyncio.wait_for(
        reader.readuntil(b"\x03"),
        timeout=config.body_timeout
    )
    
    # Phase 3: Read checksum byte
    response += await asyncio.wait_for(
        reader.readexactly(1),
        timeout=config.checksum_timeout
    )
    
    log_payload(logger, "RX", response, "response")
    return response


async def fetch(message: bytes) -> bytes:
    """
    Send message to IO Board and receive response with retry logic.
    
    This function implements thread-safe serial communication with:
    - Mutex-based exclusive access
    - Exponential backoff retry strategy
    - Comprehensive error handling and logging
    - Automatic connection management
    
    Args:
        message: Binary protocol message to send
        
    Returns:
        Binary protocol response from device
        
    Raises:
        SerialCommunicationError: If communication fails after all retries
    """
    config = get_serial_config()
    
    async with _serial_mutex:
        with PerformanceLogger(logger, "serial_fetch", port=config.port):
            logger.debug(f"Opening serial port: {config.port} @ {config.baudrate} baud")
            reader, writer = await get_serial_connection()
            
            try:
                # Retry loop with exponential backoff
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
                
                # All retries exhausted
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
                    
            finally:
                # Always close the connection
                logger.debug("Closing serial port")
                writer.close()
                await writer.wait_closed()