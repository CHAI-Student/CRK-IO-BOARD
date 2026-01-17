"""
Type definitions and data models for IO Board protocol.

This module defines type-safe structures for protocol messages, commands,
and data payloads using TypedDicts, enums, and Pydantic models.
"""

from enum import Enum
from typing import List, TypedDict, Union

from pydantic import BaseModel, Field, field_validator


class CommandType(str, Enum):
    """Protocol command types."""
    
    MANAGEMENT_CONTROL = "MC"
    REQUEST = "RQ"


class ManagementSubcommand(str, Enum):
    """Management control subcommands."""
    
    INITIALIZE = "PD"
    DOOR_CONTROL = "DC"
    CALIBRATE = "LZ"
    WRITE_PRODUCT_ID = "WP"
    CLEAR_ERRORS = "EZ"
    REBOOT = "RT"


class RequestSubcommand(str, Enum):
    """Request subcommands."""
    
    MANUFACTURING_INFO = "MI"
    LOADCELL_WEIGHTS = "IW"
    IO_STATUS = "ID"
    ERROR_LIST = "ER"


class DoorState(str, Enum):
    """Door/deadbolt state values."""
    
    OPEN = "OPEN"
    CLOSE = "CLOSE"


class DoorStateByte(int, Enum):
    """Door state byte values for protocol encoding."""
    
    OPEN = ord("O")
    CLOSE = ord("C")


# Protocol message structures (for internal use)

class ProtocolHeader(TypedDict):
    """Protocol message header."""
    
    COMMAND: str
    SUBCOMMAND: str


class DoorControlData(TypedDict):
    """Door control command data."""
    
    DOOR: Union[DoorStateByte, str]


class ProductIDData(TypedDict):
    """Product ID data."""
    
    PRODUCT_ID: str


class ManufacturingInfoData(TypedDict):
    """Manufacturing information response data."""
    
    PRODUCT_ID: str
    SW_VERSION: str


class LoadcellsData(TypedDict):
    """Loadcell readings response data."""
    
    LOADCELLS: List[str]


class IOStatusData(TypedDict):
    """IO status response data."""
    
    DOOR: str
    DEADBOLT: str


class ErrorsData(TypedDict):
    """Error list response data."""
    
    ERRORS: List[str]


# API request/response models (Pydantic)

class DeadboltRequest(BaseModel):
    """Request model for deadbolt control."""
    
    state: DoorState = Field(
        ...,
        description="Desired deadbolt state",
        examples=["OPEN", "CLOSE"]
    )


class DeadboltResponse(BaseModel):
    """Response model for deadbolt control."""
    
    state: DoorState = Field(
        ...,
        description="Current deadbolt state",
        examples=["OPEN", "CLOSE"]
    )


class ManufacturingNumberRequest(BaseModel):
    """Request model for setting manufacturing number."""
    
    manufacturing_number: str = Field(
        ...,
        min_length=11,
        max_length=11,
        description="11-character manufacturing/product ID",
        examples=["ABC12345678"]
    )
    
    @field_validator("manufacturing_number")
    @classmethod
    def validate_alphanumeric(cls, v: str) -> str:
        """Validate manufacturing number is alphanumeric."""
        if not v.replace(" ", "").isalnum():
            raise ValueError("Manufacturing number must be alphanumeric")
        return v


class ManufacturingNumberResponse(BaseModel):
    """Response model for manufacturing number."""
    
    manufacturing_number: str = Field(
        ...,
        min_length=11,
        max_length=11,
        description="11-character manufacturing/product ID",
        examples=["ABC12345678"]
    )


class ProductInfoResponse(BaseModel):
    """Response model for product information."""
    
    product_id: str = Field(
        ...,
        description="Product/manufacturing ID",
        examples=["ABC12345678"]
    )
    sw_version: str = Field(
        ...,
        description="Software/firmware version",
        examples=["01", "12"]
    )


class LoadCellsResponse(BaseModel):
    """Response model for loadcell readings."""
    
    loadcells: List[str] = Field(
        ...,
        description="Array of 10 loadcell readings (6 chars each: +/-XXXXX or EEEEEE/VVVVVV for errors)",
        min_length=10,
        max_length=10,
        examples=[["+12345", "-00123", "+99999", "-12345", "+00000", "-00001", "+54321", "-99999", "+11111", "-22222"]]
    )
    
    @field_validator("loadcells")
    @classmethod
    def validate_loadcell_format(cls, v: List[str]) -> List[str]:
        """Validate each loadcell reading is 6 characters."""
        for reading in v:
            if len(reading) != 6:
                raise ValueError(f"Each loadcell reading must be exactly 6 characters, got: {reading}")
        return v


class IOStatusResponse(BaseModel):
    """Response model for IO status."""
    
    door: str = Field(
        ...,
        description="Door sensor status (6 characters)",
        min_length=6,
        max_length=6,
        examples=["OPENED", "CLOSED", "ERROR_"]
    )
    deadbolt: str = Field(
        ...,
        description="Deadbolt sensor status (6 characters)",
        min_length=6,
        max_length=6,
        examples=["OPENED", "CLOSED", "ERROR_"]
    )


class ErrorItem(BaseModel):
    """Single error code item."""
    
    code: str = Field(
        ...,
        description="4-character error code",
        min_length=4,
        max_length=4,
        examples=["E001", "W002", "0000"]
    )


class ErrorListResponse(BaseModel):
    """Response model for error list."""
    
    errors: List[ErrorItem] = Field(
        ...,
        description="Array of up to 4 error codes",
        max_length=4,
        examples=[[{"code": "E001"}, {"code": "0000"}]]
    )


class StandardErrorResponse(BaseModel):
    """Standard error response format."""
    
    error_code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["E2001", "E3002"]
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Serial port not found", "Failed to parse protocol response"]
    )
    details: dict = Field(
        default_factory=dict,
        description="Additional error context",
        examples=[{"port": "COM3", "baudrate": 38400}]
    )


class SuccessResponse(BaseModel):
    """Standard success response for operations without specific return data."""
    
    success: bool = Field(
        default=True,
        description="Operation success indicator"
    )
    message: str = Field(
        default="Operation completed successfully",
        description="Success message"
    )


# SSE Event Models for Streaming Endpoints

class LoadcellUpdateEvent(BaseModel):
    """Periodic loadcell update event data (SSE event: loadcell.update)."""
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of the reading",
        examples=["2026-01-17T14:30:45.123456"]
    )
    raw_values: List[str] = Field(
        ...,
        description="Raw 10 loadcell readings (6 chars each)",
        min_length=10,
        max_length=10,
        examples=[["+12345", "+00123", "-00456", "+99999", "+00000", "EEEEEE", "+11111", "+22222", "+33333", "+44444"]]
    )
    filtered_values: List[str] = Field(
        ...,
        description="Filtered 10 loadcell readings (6 chars each)",
        min_length=10,
        max_length=10,
        examples=[["+12340", "+00120", "-00450", "+99995", "+00000", "EEEEEE", "+11110", "+22220", "+33330", "+44440"]]
    )
    filter_method: str = Field(
        ...,
        description="Filter method applied (none, exponential, kalman)",
        examples=["exponential"]
    )


class LoadcellChangeEvent(BaseModel):
    """Loadcell threshold change event data (SSE event: loadcell.change)."""
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp when change detected",
        examples=["2026-01-17T14:30:45.123456"]
    )
    changed_indices: List[int] = Field(
        ...,
        description="Indices (0-9) of loadcells that exceeded threshold",
        examples=[[0, 3, 7]]
    )
    old_values: List[float] = Field(
        ...,
        description="Previous values for changed loadcells",
        examples=[[12345.0, 99999.0, 11111.0]]
    )
    new_values: List[float] = Field(
        ...,
        description="New values for changed loadcells",
        examples=[[12350.0, 99990.0, 11120.0]]
    )
    deltas: List[float] = Field(
        ...,
        description="Absolute change amounts for changed loadcells",
        examples=[[5.0, 9.0, 9.0]]
    )
    threshold: float = Field(
        ...,
        description="Threshold value that was exceeded",
        examples=[5.0]
    )
    threshold_scope: str = Field(
        ...,
        description="Scope of threshold comparison (raw or filtered)",
        examples=["filtered"]
    )


class LoadcellUncertaintyEvent(BaseModel):
    """Loadcell uncertainty/error event data (SSE event: loadcell.uncertainty)."""
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp when uncertainty detected",
        examples=["2026-01-17T14:30:45.123456"]
    )
    affected_indices: List[int] = Field(
        ...,
        description="Indices (0-9) of loadcells with uncertainty/errors",
        examples=[[5, 8]]
    )
    reason: str = Field(
        ...,
        description="Reason for uncertainty (error_state, parse_failure, io_board_failure)",
        examples=["error_state"]
    )
    details: dict = Field(
        default_factory=dict,
        description="Additional context about the uncertainty",
        examples=[{"error_values": ["EEEEEE", "VVVVVV"]}]
    )


class DoorUpdateEvent(BaseModel):
    """Door status update event data (SSE event: door.update)."""
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of the reading",
        examples=["2026-01-17T14:30:45.123456"]
    )
    door: str = Field(
        ...,
        description="Door sensor status (6 characters)",
        min_length=6,
        max_length=6,
        examples=["OPENED", "CLOSED", "ERROR_"]
    )
    deadbolt: str = Field(
        ...,
        description="Deadbolt sensor status (6 characters)",
        min_length=6,
        max_length=6,
        examples=["OPENED", "CLOSED", "ERROR_"]
    )
