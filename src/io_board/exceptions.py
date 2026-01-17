"""
Custom exception hierarchy for IO Board module.

This module defines a comprehensive exception hierarchy for granular error handling
and provides error codes for client-side consumption.
"""

from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    """Standard error codes for API responses."""
    
    # Configuration errors (1xxx)
    CONFIG_INVALID = "E1001"
    CONFIG_MISSING = "E1002"
    
    # Serial communication errors (2xxx)
    SERIAL_PORT_NOT_FOUND = "E2001"
    SERIAL_PORT_BUSY = "E2002"
    SERIAL_PORT_PERMISSION_DENIED = "E2003"
    SERIAL_CONNECTION_FAILED = "E2004"
    SERIAL_TIMEOUT = "E2005"
    SERIAL_READ_ERROR = "E2006"
    SERIAL_WRITE_ERROR = "E2007"
    SERIAL_INCOMPLETE_READ = "E2008"
    
    # Protocol errors (3xxx)
    PROTOCOL_BUILD_FAILED = "E3001"
    PROTOCOL_PARSE_FAILED = "E3002"
    PROTOCOL_CHECKSUM_MISMATCH = "E3003"
    PROTOCOL_INVALID_COMMAND = "E3004"
    PROTOCOL_INVALID_RESPONSE = "E3005"
    PROTOCOL_MALFORMED_DATA = "E3006"
    
    # Validation errors (4xxx)
    VALIDATION_INVALID_INPUT = "E4001"
    VALIDATION_OUT_OF_RANGE = "E4002"
    VALIDATION_INVALID_FORMAT = "E4003"
    VALIDATION_MISSING_REQUIRED = "E4004"
    
    # Device errors (5xxx)
    DEVICE_NOT_INITIALIZED = "E5001"
    DEVICE_BUSY = "E5002"
    DEVICE_ERROR_STATE = "E5003"
    DEVICE_COMMAND_FAILED = "E5004"
    
    # Internal errors (9xxx)
    INTERNAL_ERROR = "E9001"
    UNKNOWN_ERROR = "E9999"


class IOBoardError(Exception):
    """Base exception for all IO Board errors."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[dict] = None
    ) -> None:
        """
        Initialize IO Board error.
        
        Args:
            message: Human-readable error message
            error_code: Standard error code for client identification
            details: Additional error context (should not contain sensitive data)
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> dict:
        """
        Convert exception to dictionary for API responses.
        
        Returns:
            Dictionary with error code, message, and details
        """
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(IOBoardError):
    """Configuration-related errors."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.CONFIG_INVALID,
        details: Optional[dict] = None
    ) -> None:
        """Initialize configuration error."""
        super().__init__(message, error_code, details)


class SerialCommunicationError(IOBoardError):
    """Serial communication errors."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.SERIAL_CONNECTION_FAILED,
        details: Optional[dict] = None
    ) -> None:
        """Initialize serial communication error."""
        super().__init__(message, error_code, details)


class ProtocolError(IOBoardError):
    """Protocol encoding/decoding errors."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.PROTOCOL_PARSE_FAILED,
        details: Optional[dict] = None
    ) -> None:
        """Initialize protocol error."""
        super().__init__(message, error_code, details)


class ValidationError(IOBoardError):
    """Input validation errors."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.VALIDATION_INVALID_INPUT,
        details: Optional[dict] = None
    ) -> None:
        """Initialize validation error."""
        super().__init__(message, error_code, details)


class DeviceError(IOBoardError):
    """Device operation errors."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.DEVICE_COMMAND_FAILED,
        details: Optional[dict] = None
    ) -> None:
        """Initialize device error."""
        super().__init__(message, error_code, details)
