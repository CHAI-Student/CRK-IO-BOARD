"""IO Board 서비스 커스텀 예외 계층.

세분화된 에러 처리를 위한 예외 계층과 클라이언트가 소비할 수 있는
표준 에러 코드(E1xxx~E9xxx)를 정의한다.
"""

from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    """API 응답용 표준 에러 코드."""

    # 설정 에러 (1xxx)
    CONFIG_INVALID = "E1001"
    CONFIG_MISSING = "E1002"
    
    # serial 통신 에러 (2xxx)
    SERIAL_PORT_NOT_FOUND = "E2001"
    SERIAL_PORT_BUSY = "E2002"
    SERIAL_PORT_PERMISSION_DENIED = "E2003"
    SERIAL_CONNECTION_FAILED = "E2004"
    SERIAL_TIMEOUT = "E2005"
    SERIAL_READ_ERROR = "E2006"
    SERIAL_WRITE_ERROR = "E2007"
    SERIAL_INCOMPLETE_READ = "E2008"
    
    # protocol 에러 (3xxx)
    PROTOCOL_BUILD_FAILED = "E3001"
    PROTOCOL_PARSE_FAILED = "E3002"
    PROTOCOL_CHECKSUM_MISMATCH = "E3003"
    PROTOCOL_INVALID_COMMAND = "E3004"
    PROTOCOL_INVALID_RESPONSE = "E3005"
    PROTOCOL_MALFORMED_DATA = "E3006"
    
    # 입력 검증 에러 (4xxx)
    VALIDATION_INVALID_INPUT = "E4001"
    VALIDATION_OUT_OF_RANGE = "E4002"
    VALIDATION_INVALID_FORMAT = "E4003"
    VALIDATION_MISSING_REQUIRED = "E4004"
    
    # 디바이스 에러 (5xxx)
    DEVICE_NOT_INITIALIZED = "E5001"
    DEVICE_BUSY = "E5002"
    DEVICE_ERROR_STATE = "E5003"
    DEVICE_COMMAND_FAILED = "E5004"
    
    # 내부 에러 (9xxx)
    INTERNAL_ERROR = "E9001"
    UNKNOWN_ERROR = "E9999"


class IOBoardError(Exception):
    """모든 IO Board 에러의 base 예외.

    Args:
        message: 사람이 읽을 수 있는 에러 메시지
        error_code: 클라이언트 식별용 표준 에러 코드
        details: 추가 에러 컨텍스트 (민감 정보 포함 금지)
    """

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[dict] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> dict:
        """API 응답용 딕셔너리(error_code/message/details)로 변환한다."""
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(IOBoardError):
    """설정 관련 에러."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.CONFIG_INVALID,
        details: Optional[dict] = None
    ) -> None:
        super().__init__(message, error_code, details)


class SerialCommunicationError(IOBoardError):
    """serial 통신 에러."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.SERIAL_CONNECTION_FAILED,
        details: Optional[dict] = None
    ) -> None:
        super().__init__(message, error_code, details)


class ProtocolError(IOBoardError):
    """protocol 인코딩/디코딩 에러."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.PROTOCOL_PARSE_FAILED,
        details: Optional[dict] = None
    ) -> None:
        super().__init__(message, error_code, details)


class ValidationError(IOBoardError):
    """입력 검증 에러."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.VALIDATION_INVALID_INPUT,
        details: Optional[dict] = None
    ) -> None:
        super().__init__(message, error_code, details)


class DeviceError(IOBoardError):
    """디바이스 동작 에러."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.DEVICE_COMMAND_FAILED,
        details: Optional[dict] = None
    ) -> None:
        super().__init__(message, error_code, details)
