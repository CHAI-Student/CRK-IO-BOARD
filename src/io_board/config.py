"""
Configuration management for IO Board module.

This module provides enterprise-grade configuration management using environment
variables with validation and type safety.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SerialConfig:
    """Serial port configuration settings."""
    
    port: str
    baudrate: int
    header_timeout: float
    body_timeout: float
    checksum_timeout: float
    max_retries: int
    initial_retry_delay: float
    retry_backoff_multiplier: float
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.baudrate <= 0:
            raise ValueError(f"Baudrate must be positive, got {self.baudrate}")
        if self.header_timeout <= 0:
            raise ValueError(f"Header timeout must be positive, got {self.header_timeout}")
        if self.body_timeout <= 0:
            raise ValueError(f"Body timeout must be positive, got {self.body_timeout}")
        if self.checksum_timeout <= 0:
            raise ValueError(f"Checksum timeout must be positive, got {self.checksum_timeout}")
        if self.max_retries < 1:
            raise ValueError(f"Max retries must be at least 1, got {self.max_retries}")
        if self.initial_retry_delay <= 0:
            raise ValueError(f"Initial retry delay must be positive, got {self.initial_retry_delay}")
        if self.retry_backoff_multiplier < 1.0:
            raise ValueError(f"Retry backoff multiplier must be >= 1.0, got {self.retry_backoff_multiplier}")


@dataclass(frozen=True)
class APIConfig:
    """API server configuration settings."""
    
    host: str
    port: int
    log_level: str
    stream_interval: float
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {self.port}")
        if self.log_level not in ["critical", "error", "warning", "info", "debug", "trace"]:
            raise ValueError(f"Invalid log level: {self.log_level}")
        if self.stream_interval <= 0:
            raise ValueError(f"Stream interval must be positive, got {self.stream_interval}")


@dataclass(frozen=True)
class Config:
    """Global application configuration."""
    
    serial: SerialConfig
    api: APIConfig


def load_config() -> Config:
    """
    Load configuration from environment variables.
    
    Returns:
        Config: Validated configuration object
        
    Raises:
        ValueError: If configuration values are invalid
        
    Environment Variables:
        IO_BOARD_PORT: Serial port path (default: COM3)
        IO_BOARD_BAUDRATE: Serial baudrate (default: 38400)
        IO_BOARD_HEADER_TIMEOUT: Header read timeout in seconds (default: 0.5)
        IO_BOARD_BODY_TIMEOUT: Body read timeout in seconds (default: 2.0)
        IO_BOARD_CHECKSUM_TIMEOUT: Checksum read timeout in seconds (default: 0.5)
        IO_BOARD_MAX_RETRIES: Maximum number of retry attempts (default: 3)
        IO_BOARD_INITIAL_RETRY_DELAY: Initial retry delay in seconds (default: 0.1)
        IO_BOARD_RETRY_BACKOFF: Retry backoff multiplier (default: 2.0)
        IO_BOARD_API_HOST: API server host (default: 0.0.0.0)
        IO_BOARD_API_PORT: API server port (default: 8000)
        IO_BOARD_API_LOG_LEVEL: API log level (default: info)
        IO_BOARD_STREAM_INTERVAL: SSE stream update interval in seconds (default: 0.5)
    """
    serial_config = SerialConfig(
        port=os.getenv("IO_BOARD_PORT", "COM3"),
        baudrate=int(os.getenv("IO_BOARD_BAUDRATE", "38400")),
        header_timeout=float(os.getenv("IO_BOARD_HEADER_TIMEOUT", "0.5")),
        body_timeout=float(os.getenv("IO_BOARD_BODY_TIMEOUT", "2.0")),
        checksum_timeout=float(os.getenv("IO_BOARD_CHECKSUM_TIMEOUT", "0.5")),
        max_retries=int(os.getenv("IO_BOARD_MAX_RETRIES", "3")),
        initial_retry_delay=float(os.getenv("IO_BOARD_INITIAL_RETRY_DELAY", "0.1")),
        retry_backoff_multiplier=float(os.getenv("IO_BOARD_RETRY_BACKOFF", "2.0")),
    )
    
    api_config = APIConfig(
        host=os.getenv("IO_BOARD_API_HOST", "0.0.0.0"),
        port=int(os.getenv("IO_BOARD_API_PORT", "8000")),
        log_level=os.getenv("IO_BOARD_API_LOG_LEVEL", "info"),
        stream_interval=float(os.getenv("IO_BOARD_STREAM_INTERVAL", "0.5")),
    )
    
    return Config(serial=serial_config, api=api_config)
