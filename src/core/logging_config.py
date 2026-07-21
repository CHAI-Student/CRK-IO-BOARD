"""IO Board 서비스 구조화 로깅 설정.

correlation ID 추적, 구조화된 출력 포맷, 성능 측정
(PerformanceLogger), serial payload hex 덤프(log_payload)를 포함한
중앙집중식 로깅 설정을 제공한다.
"""

import contextvars
import logging
import time
from typing import Any, Optional
import uuid


# correlation ID 추적용 context variable
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


class CorrelationIdFilter(logging.Filter):
    """로그 레코드에 correlation ID를 추가하는 logging filter."""

    def filter(self, record: logging.LogRecord) -> bool:
        """로그 레코드에 correlation ID를 붙인다 (항상 통과)."""
        record.correlation_id = correlation_id_var.get() or "N/A"
        return True


class StructuredFormatter(logging.Formatter):
    """필드 순서가 일정한 구조화 로그 formatter."""

    def format(self, record: logging.LogRecord) -> str:
        """[시각][레벨][correlation ID][로거명] 메시지 형태로 포맷한다."""
        # 구조화 로그 메시지 조립
        parts = [
            f"[{self.formatTime(record, self.datefmt)}]",
            f"[{record.levelname}]",
            f"[{getattr(record, 'correlation_id', 'N/A')}]",
            f"[{record.name}]",
            record.getMessage(),
        ]
        
        # 예외 정보가 있으면 덧붙인다
        if record.exc_info:
            parts.append("\n" + self.formatException(record.exc_info))
        
        return " ".join(parts)


def setup_logging(log_level: str = "INFO") -> None:
    """애플리케이션의 구조화 로깅을 설정한다.

    Args:
        log_level: 로깅 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # 레벨 문자열을 상수로 변환
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    for name in ["api", "core", "io_board", "services"]:
        # 최상위 패키지별 로거 설정
        logger = logging.getLogger(name)
        logger.setLevel(numeric_level)

        # 기존 handler 제거 (중복 로그 방지)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 구조화 formatter를 적용한 콘솔 handler 생성
        handler = logging.StreamHandler()
        handler.setLevel(numeric_level)

        formatter = StructuredFormatter(
            fmt="%(asctime)s.%(msecs)03d %(message)s",
        )
        formatter.default_msec_format = "%s.%03d"
        handler.setFormatter(formatter)

        # correlation ID filter 추가
        handler.addFilter(CorrelationIdFilter())

        logger.addHandler(handler)

        # root 로거로의 전파 차단
        logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """지정 이름의 로거 인스턴스를 반환한다.

    Args:
        name: 로거 이름 (보통 모듈의 __name__)

    Returns:
        설정된 로거 인스턴스
    """
    return logging.getLogger(f"io_board.{name}")


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """현재 컨텍스트의 correlation ID를 설정한다.

    Args:
        correlation_id: 설정할 correlation ID (None이면 UUID 생성)

    Returns:
        설정된 correlation ID
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """현재 correlation ID를 반환한다 (미설정 시 None)."""
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    """현재 correlation ID를 초기화한다."""
    correlation_id_var.set(None)


class PerformanceLogger:
    """작업 소요 시간을 로깅하는 context manager."""

    def __init__(self, logger: logging.Logger, operation: str, **context: Any) -> None:
        """
        Args:
            logger: 사용할 로거 인스턴스
            operation: 측정 대상 작업 이름
            **context: 로그에 함께 남길 추가 컨텍스트
        """
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time: Optional[float] = None

    def __enter__(self) -> "PerformanceLogger":
        """측정 시작."""
        self.start_time = time.perf_counter()
        context_str = " ".join(f"{k}={v}" for k, v in self.context.items())
        self.logger.debug(f"Starting {self.operation} {context_str}".strip())
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """측정을 종료하고 소요 시간(성공/실패)을 로깅한다."""
        if self.start_time is None:
            return
        
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        context_str = " ".join(f"{k}={v}" for k, v in self.context.items())
        
        if exc_type is None:
            self.logger.debug(
                f"Completed {self.operation} in {duration_ms:.2f}ms {context_str}".strip()
            )
        else:
            self.logger.error(
                f"Failed {self.operation} after {duration_ms:.2f}ms {context_str} "
                f"error={exc_type.__name__}".strip()
            )


def log_payload(logger: logging.Logger, direction: str, data: bytes, label: str = "") -> None:
    """바이너리 payload를 hex 형식으로 로깅한다.

    Args:
        logger: 사용할 로거 인스턴스
        direction: 방향 표시 (예: "TX", "RX")
        data: 로깅할 바이너리 데이터
        label: payload에 붙일 선택적 라벨
    """
    hex_data = data.hex().upper()
    # 공백으로 구분한 hex 쌍으로 포맷
    formatted = " ".join(hex_data[i:i+2] for i in range(0, len(hex_data), 2))
    label_str = f" {label}" if label else ""
    logger.debug(f"{direction}{label_str}: {formatted} ({len(data)} bytes)")
