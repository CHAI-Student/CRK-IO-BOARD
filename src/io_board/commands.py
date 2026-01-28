"""
High-level command interface for IO Board operations.

This module provides a business logic layer that separates high-level device
commands from low-level protocol details. All functions include comprehensive
type hints, docstrings, and error handling.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List

from .exceptions import DeviceError, ErrorCode, ValidationError
from .logging_config import PerformanceLogger, get_logger
from .protocol import build_request, parse_response
from .serial_io import fetch
from .io_types import (
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
        ValidationError: If command/subcommand types mismatch
        ProtocolError: If protocol building/parsing fails
        SerialCommunicationError: If serial communication fails
    """
    
    if command == CommandType.MANAGEMENT_CONTROL and not isinstance(subcommand, ManagementSubcommand):
        raise ValidationError("Mismatched subcommand type for MANAGEMENT_CONTROL command")
    if command == CommandType.REQUEST and not isinstance(subcommand, RequestSubcommand):
        raise ValidationError("Mismatched subcommand type for REQUEST command")

    with PerformanceLogger(logger, "command", cmd=f"{command.value}/{subcommand.value}"):
        # Build request message
        request_message = build_request(command.value, subcommand.value, data)

        while True:
            # Send and receive via serial
            response_message = await fetch(request_message)
            
            # Parse response
            response = parse_response(response_message)

            # Validate response command and subcommand
            if response.COMMAND != command.value or response.SUBCOMMAND != subcommand.value:
                logger.warning(
                    f"Unexpected response CMD/SUBCMD: "
                    f"expected {command.value}/{subcommand.value}, "
                    f"got {response.COMMAND}/{response.SUBCOMMAND}. Retrying..."
                )
                continue  # Retry on unexpected response
            
            return response

@asynccontextmanager
async def _session(command: str, **kwargs) -> AsyncIterator[None]:
    try:
        yield
    except DeviceError as e:
        raise DeviceError(
            f"Command '{command}' failed"            ,
            ErrorCode.DEVICE_COMMAND_FAILED,
            {'command': command} | kwargs
        ) from e


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
    async with _session('initialize'):
        logger.info("Initializing IO Board")
        await _send_command(
            CommandType.MANAGEMENT_CONTROL,
            ManagementSubcommand.INITIALIZE,
            {}
        )
        logger.info("IO Board initialized")


async def set_deadbolt(action: DeadboltAction) -> DeadboltState:
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
    """
    Calibrate the IO Board sensors (loadcells).
    
    This command initiates a calibration sequence for all weight sensors.
    The device should be in an unloaded state before calibration.
    
    Raises:
        DeviceError: If calibration fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
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
    """
    Clear the device error log.
    
    This command clears all stored error codes from the device's error history.
    
    Raises:
        DeviceError: If clearing errors fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
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
    """
    Reboot the IO Board device.
    
    This command initiates a device restart. The device will be unavailable
    for a few seconds during the reboot process.
    
    Raises:
        DeviceError: If reboot command fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
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
    """
    Get device manufacturing information.
    
    Returns:
        Dictionary with 'product_id' (11 chars) and 'sw_version' (2 chars)
        
    Raises:
        DeviceError: If getting product info fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
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
    async with _session('get_loadcells'):
        logger.debug("Getting loadcell values")
        response = await _send_command(
            CommandType.REQUEST,
            RequestSubcommand.LOADCELL_WEIGHTS,
            {}
        )
        result = list(response.DATA.LOADCELLS)
        logger.debug(f"Loadcell values retrieved: {result}")
        return result


async def get_status() -> IOStatusData:
    """
    Get door and deadbolt sensor status.
    
    Returns:
        StatusData with 'door' and 'deadbolt' status values.
        
    Raises:
        DeviceError: If getting IO status fails
        ProtocolError: If protocol communication fails
        SerialCommunicationError: If serial communication fails
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
