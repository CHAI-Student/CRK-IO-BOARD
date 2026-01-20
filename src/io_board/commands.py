"""
High-level command interface for IO Board operations.

This module provides a business logic layer that separates high-level device
commands from low-level protocol details. All functions include comprehensive
type hints, docstrings, and error handling.
"""

import asyncio
from typing import Any, Dict, List

from .exceptions import DeviceError, ErrorCode
from .logging_config import PerformanceLogger, get_logger
from .protocol import build_request, parse_response
from .serial_io import fetch
from .io_types import (
    CommandType,
    DoorState,
    DoorStateByte,
    ManagementSubcommand,
    RequestSubcommand,
)

logger = get_logger(__name__)


async def _send_command(
    command: CommandType,
    subcommand: str,
    data: Dict[str, Any]
) -> Any:
    """
    Send a command to the IO Board and return parsed response.
    
    This internal helper combines protocol building, serial communication,
    and response parsing with error handling and logging.
    
    Args:
        command: Command type (MC or RQ)
        subcommand: Specific subcommand code
        data: Command-specific data payload
        
    Returns:
        Parsed response structure
        
    Raises:
        ProtocolError: If protocol building/parsing fails
        SerialCommunicationError: If serial communication fails
    """
    with PerformanceLogger(logger, "command", cmd=f"{command.value}{subcommand}"):
        # Build request message
        request_message = build_request(command.value, subcommand, data)

        while True:
            # Send and receive via serial
            response_message = await fetch(request_message)
            
            # Parse response
            response = parse_response(response_message)

            if response.COMMAND != command.value or response.SUBCOMMAND != subcommand:
                logger.warning(
                    f"Unexpected response CMD/SUBCMD: "
                    f"expected {command.value}/{subcommand}, "
                    f"got {response.COMMAND}/{response.SUBCOMMAND}. Retrying..."
                )
                continue  # Retry on unexpected response
            
            return response


async def initialize() -> None:
    """
    Initialize the IO Board device.
    
    This command should be called once after device power-on or reset
    to initialize all subsystems.
    
    Raises:
        DeviceError: If initialization fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.info("Initializing IO Board")
    try:
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.INITIALIZE.value,
            {}
        )
        logger.info("IO Board initialized successfully")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize IO Board: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Device initialization failed",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "initialize"}
            ) from e
        raise


async def set_door_state(state: DoorState) -> DoorState:
    """
    Control the door lock/deadbolt.
    
    Args:
        state: Desired door state (OPEN or CLOSE)
        
    Returns:
        Actual door state after command execution
        
    Raises:
        DeviceError: If door control fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.info(f"Setting door state: {state.value}")
    try:
        response = await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.DOOR_CONTROL.value,
            {"DOOR": DoorStateByte[state.value]}
        )
        
        # Convert response byte back to DoorState
        door_byte = response.DATA.DOOR
        result_state = DoorState.OPEN if door_byte == DoorStateByte.OPEN else DoorState.CLOSE
        
        logger.info(f"Door state set to: {result_state.value}")
        return result_state
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to set door state: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                f"Failed to set door state to {state.value}",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "set_door_state", "state": state.value}
            ) from e
        raise


async def calibrate() -> None:
    """
    Calibrate the IO Board sensors (loadcells).
    
    This command initiates a calibration sequence for all weight sensors.
    The device should be in an unloaded state before calibration.
    
    Raises:
        DeviceError: If calibration fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.info("Starting IO Board calibration")
    try:
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.CALIBRATE.value,
            {}
        )
        logger.info("IO Board calibration completed")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to calibrate IO Board: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Device calibration failed",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "calibrate"}
            ) from e
        raise


async def set_manufacturing_number(manufacturing_number: str) -> str:
    """
    Set the device manufacturing/product ID.
    
    Args:
        manufacturing_number: 11-character alphanumeric product ID
        
    Returns:
        Manufacturing number as confirmed by device (echoed back)
        
    Raises:
        DeviceError: If setting manufacturing number fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
        ValidationError: If manufacturing number format is invalid
    """
    logger.info(f"Setting manufacturing number: {manufacturing_number}")
    try:
        response = await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.WRITE_PRODUCT_ID.value,
            {"PRODUCT_ID": manufacturing_number}
        )
        
        result = response.DATA.PRODUCT_ID
        logger.info(f"Manufacturing number set: {result}")
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to set manufacturing number: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Failed to set manufacturing number",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "set_manufacturing_number", "value": manufacturing_number}
            ) from e
        raise


async def clear_errors() -> None:
    """
    Clear the device error log.
    
    This command clears all stored error codes from the device's error history.
    
    Raises:
        DeviceError: If clearing errors fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.info("Clearing IO Board error log")
    try:
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.CLEAR_ERRORS.value,
            {}
        )
        logger.info("IO Board error log cleared")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to clear error log: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Failed to clear error log",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "clear_errors"}
            ) from e
        raise


async def reboot() -> None:
    """
    Reboot the IO Board device.
    
    This command initiates a device restart. The device will be unavailable
    for a few seconds during the reboot process.
    
    Raises:
        DeviceError: If reboot command fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.info("Rebooting IO Board")
    try:
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.REBOOT.value,
            {}
        )
        logger.info("IO Board reboot initiated")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to reboot IO Board: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Device reboot failed",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "reboot"}
            ) from e
        raise


async def get_product_info() -> Dict[str, str]:
    """
    Get device manufacturing information.
    
    Returns:
        Dictionary with 'product_id' (11 chars) and 'sw_version' (2 chars)
        
    Raises:
        DeviceError: If getting product info fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.debug("Getting product info")
    try:
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.MANUFACTURING_INFO.value,
            {}
        )
        
        result = {
            "product_id": response.DATA.PRODUCT_ID,
            "sw_version": response.DATA.SW_VERSION,
        }
        logger.debug(f"Product info: {result}")
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to get product info: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Failed to get product info",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "get_product_info"}
            ) from e
        raise


async def get_loadcells() -> List[str]:
    """
    Get current loadcell weight readings.
    
    Returns:
        List of 10 loadcell readings (6 characters each).
        Format: "+XXXXX" or "-XXXXX" for valid readings,
                "EEEEEE" for error, "VVVVVV" for invalid
        
    Raises:
        DeviceError: If getting loadcell data fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.debug("Getting loadcell readings")
    try:
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.LOADCELL_WEIGHTS.value,
            {}
        )
        
        result = list(response.DATA.LOADCELLS)
        logger.debug(f"Loadcells: {result}")
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to get loadcell readings: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Failed to get loadcell readings",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "get_loadcells"}
            ) from e
        raise


async def get_io_status() -> Dict[str, str]:
    """
    Get door and deadbolt sensor status.
    
    Returns:
        Dictionary with 'door' and 'deadbolt' status strings (6 chars each).
        Common values: "OPENED", "CLOSED", "ERROR_"
        
    Raises:
        DeviceError: If getting IO status fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.debug("Getting IO status")
    try:
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.IO_STATUS.value,
            {}
        )
        
        result = {
            "door": response.DATA.DOOR,
            "deadbolt": response.DATA.DEADBOLT,
        }
        logger.debug(f"IO status: {result}")
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to get IO status: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Failed to get IO status",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "get_io_status"}
            ) from e
        raise


async def get_errors() -> List[str]:
    """
    Get device error history.
    
    Returns:
        List of up to 4 error codes (4 characters each).
        "0000" indicates no error in that slot.
        
    Raises:
        DeviceError: If getting error list fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
    """
    logger.debug("Getting error list")
    try:
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.ERROR_LIST.value,
            {}
        )
        
        result = list(response.DATA.ERRORS)
        logger.debug(f"Errors: {result}")
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to get error list: {e}")
        if not isinstance(e, (DeviceError,)):
            raise DeviceError(
                "Failed to get error list",
                ErrorCode.DEVICE_COMMAND_FAILED,
                {"command": "get_errors"}
            ) from e
        raise
