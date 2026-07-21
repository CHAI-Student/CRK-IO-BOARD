"""
Configuration management for IO Board module.

This module provides enterprise-grade configuration management using environment
variables with validation and type safety.
"""

import os

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SerialModel(BaseModel):
    """Serial port configuration settings."""

    port: str = Field(
        default="COM3" if os.name == "nt" else "/dev/ttyUSB0",
        description="Serial port path",
    )
    baudrate: int = Field(
        default=38400,
        description="Serial baudrate",
    )
    header_timeout: float = Field(
        default=0.5,
        description="Header read timeout in seconds",
    )
    body_timeout: float = Field(
        default=2.0,
        description="Body read timeout in seconds",
    )
    checksum_timeout: float = Field(
        default=0.5,
        description="Checksum read timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts",
    )
    initial_retry_delay: float = Field(
        default=0.1,
        description="Initial retry delay in seconds",
    )
    retry_backoff_multiplier: float = Field(
        default=2.0,
        description="Retry backoff multiplier",
    )

    @field_validator("baudrate", mode="after")
    def validate_baudrate(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"Baudrate must be positive, got {value}")
        return value

    @field_validator("header_timeout", "body_timeout", "checksum_timeout", mode="after")
    def validate_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"Timeout must be positive, got {value}")
        return value

    @field_validator("max_retries", mode="after")
    def validate_max_retries(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"Max retries must be at least 1, got {value}")
        return value

    @field_validator("initial_retry_delay", mode="after")
    def validate_initial_retry_delay(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"Initial retry delay must be positive, got {value}")
        return value

    @field_validator("retry_backoff_multiplier", mode="after")
    def validate_retry_backoff_multiplier(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError(f"Retry backoff multiplier must be >= 1.0, got {value}")
        return value


class APIModel(BaseModel):
    """API server configuration settings."""

    host: str = Field(
        default="0.0.0.0",
        description="API server host",
    )
    port: int = Field(
        default=8000,
        description="API server port",
    )
    log_level: str = Field(
        default="info",
        description="API log level",
    )
    timeout_graceful_shutdown: int = Field(
        default=10,
        description="Graceful shutdown timeout in seconds",
    )

    @field_validator("port", mode="after")
    def validate_port(cls, value: int) -> int:
        if value <= 0 or value > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {value}")
        return value

    @field_validator("log_level", mode="after")
    def validate_log_level(cls, value: str) -> str:
        valid_levels = [
            "critical",
            "error",
            "warning",
            "info",
            "debug",
            "trace",
        ]
        if value not in valid_levels:
            raise ValueError(f"Invalid log level: {value}")
        return value
    
    @field_validator("timeout_graceful_shutdown", mode="after")
    def validate_timeout_graceful_shutdown(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"Timeout for graceful shutdown must be positive, got {value}")
        return value


class PollingModel(BaseModel):
    """Polling service configuration settings."""

    loadcells_poll_interval: float = Field(
        default=0.8,
        description="Loadcell poll interval in seconds. Keep above "
        "loadcells_min_request_gap so the recording stream gets fresh (not "
        "cached) frames.",
    )
    io_status_poll_interval: float = Field(
        default=0.5,
        description="IO status poll interval in seconds",
    )
    loadcells_min_request_gap: float = Field(
        default=0.75,
        description="Minimum spacing between loadcell serial requests; calls "
        "arriving sooner are served from cache. The firmware reports garbage "
        "signs when RQIW requests are spaced closer than ~0.7s (measured "
        "duty: 0.09s->0.89, 0.5s->0.25, 0.6s->0.03, 0.7s->0.00 — see "
        "docs/FIRMWARE_SIGN_GLITCH_REQUEST.md). 0 disables throttling.",
    )

    @field_validator("loadcells_poll_interval", "io_status_poll_interval", mode="after")
    def validate_intervals(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"Poll interval must be positive, got {value}")
        return value

    @field_validator("loadcells_min_request_gap", mode="after")
    def validate_min_request_gap(cls, value: float) -> float:
        if value < 0:
            raise ValueError(f"Min request gap must be non-negative, got {value}")
        return value


class SanitizeModel(BaseModel):
    """Loadcell reading sanitizer settings (sign-glitch fix + quantization).

    Defaults are derived from the issue #1 flicker capture: glitches are
    single-frame, magnitude-preserving sign inversions (~12% of frames),
    and the LABD-B3/K3 guaranteed resolution is 5 g.
    """

    enabled: bool = Field(
        default=True,
        description="Enable sign-glitch correction on loadcell readings",
    )
    median_filter: bool = Field(
        default=False,
        description="Median-of-3 pre-filter (adds one frame of latency). "
        "Legacy defense for sub-0.7s request spacing; unnecessary while "
        "polling.loadcells_min_request_gap >= 0.75 keeps signs clean at the "
        "source. Enable only if the throttle must be disabled.",
    )
    magnitude_tolerance_grams: float = Field(
        default=2.0,
        description="Max |magnitude| difference to treat a sign flip as a glitch",
    )
    min_magnitude_grams: float = Field(
        default=5.0,
        description="Readings below this magnitude are never corrected (zero-crossing noise)",
    )
    relatch_frames: int = Field(
        default=3,
        description="Accept an inverted sign as genuine after this many consecutive frames",
    )
    staleness_seconds: float = Field(
        default=2.0,
        description="Ignore previous reading older than this when detecting glitches",
    )
    quantize_grams: float = Field(
        default=5.0,
        description="Quantize output to this step (sensor resolution); 0 disables",
    )
    quantize_hysteresis_grams: float = Field(
        default=1.0,
        description="Extra margin before leaving the current quantization bin "
        "(prevents flapping when a reading sits on a bin boundary)",
    )

    @field_validator(
        "magnitude_tolerance_grams", "min_magnitude_grams", "staleness_seconds",
        "quantize_hysteresis_grams",
        mode="after",
    )
    def validate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError(f"Value must be non-negative, got {value}")
        return value

    @field_validator("relatch_frames", mode="after")
    def validate_relatch_frames(cls, value: int) -> int:
        if value < 2:
            raise ValueError(f"relatch_frames must be >= 2, got {value}")
        return value


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_prefix="IO_BOARD__",
        env_nested_delimiter="__",
    )

    serial: SerialModel = SerialModel()
    api: APIModel = APIModel()
    polling: PollingModel = PollingModel()
    sanitize: SanitizeModel = SanitizeModel()


if __name__ == "__main__":
    settings = Settings()
    print(settings.model_dump_json(indent=4))
