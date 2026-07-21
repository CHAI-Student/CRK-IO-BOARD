"""
Unit tests for configuration management (pydantic-settings 기반 현행 API).

Run: pytest tests/test_config_standalone.py

검증 대상:
- SerialModel/APIModel 필드 validation (구 SerialConfig/APIConfig 테스트 의도 보존)
- Settings의 기본값 로드 및 IO_BOARD__ prefix(중첩 구분자 __) 환경변수 오버라이드
  (구 load_config/IO_BOARD_PORT 테스트 의도 보존)
- 냉동고 검증 기본값(throttle/sanitizer)과 health 임계값 기본값 불변 확인
"""

import os

import pytest

# src/ import 경로는 pyproject.toml [tool.pytest.ini_options] pythonpath가 제공한다.
from core.config import (
    APIModel,
    HealthModel,
    PollingModel,
    SanitizeModel,
    SerialModel,
    Settings,
)


@pytest.fixture
def clean_env(monkeypatch):
    """IO_BOARD__* 환경변수를 모두 제거해 격리된 환경을 만든다."""
    for key in list(os.environ):
        if key.startswith("IO_BOARD__"):
            monkeypatch.delenv(key, raising=False)
    return monkeypatch


DEFAULT_SERIAL_PORT = "COM3" if os.name == "nt" else "/dev/ttyUSB0"


class TestSerialModel:
    """Test SerialModel validation."""

    def test_valid_serial_model(self):
        """Test creating valid serial configuration."""
        config = SerialModel(
            port="COM3",
            baudrate=38400,
            header_timeout=0.5,
            body_timeout=2.0,
            checksum_timeout=0.5,
            max_retries=3,
            initial_retry_delay=0.1,
            retry_backoff_multiplier=2.0,
        )
        assert config.port == "COM3"
        assert config.baudrate == 38400
        assert config.max_retries == 3

    def test_default_serial_model(self):
        """Test defaults match the documented values."""
        config = SerialModel()
        assert config.port == DEFAULT_SERIAL_PORT
        assert config.baudrate == 38400
        assert config.header_timeout == 0.5
        assert config.body_timeout == 2.0
        assert config.checksum_timeout == 0.5
        assert config.max_retries == 3
        assert config.initial_retry_delay == 0.1
        assert config.retry_backoff_multiplier == 2.0

    def test_invalid_baudrate(self):
        """Test that invalid baudrate raises ValueError."""
        with pytest.raises(ValueError, match="Baudrate must be positive"):
            SerialModel(baudrate=-1)

    def test_invalid_timeout(self):
        """Test that invalid timeout raises ValueError."""
        with pytest.raises(ValueError, match="Timeout must be positive"):
            SerialModel(header_timeout=-0.5)

    def test_invalid_max_retries(self):
        """Test that invalid max_retries raises ValueError."""
        with pytest.raises(ValueError, match="Max retries must be at least 1"):
            SerialModel(max_retries=0)

    def test_invalid_initial_retry_delay(self):
        """Test that invalid initial retry delay raises ValueError."""
        with pytest.raises(ValueError, match="Initial retry delay must be positive"):
            SerialModel(initial_retry_delay=0.0)

    def test_invalid_backoff_multiplier(self):
        """Test that invalid backoff multiplier raises ValueError."""
        with pytest.raises(ValueError, match="backoff multiplier must be"):
            SerialModel(retry_backoff_multiplier=0.5)


class TestAPIModel:
    """Test APIModel validation."""

    def test_valid_api_model(self):
        """Test creating valid API configuration."""
        config = APIModel(
            host="0.0.0.0",
            port=8000,
            log_level="info",
            timeout_graceful_shutdown=10,
        )
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.log_level == "info"
        assert config.timeout_graceful_shutdown == 10

    def test_invalid_port_too_low(self):
        """Test that port < 1 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between"):
            APIModel(port=0)

    def test_invalid_port_too_high(self):
        """Test that port > 65535 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between"):
            APIModel(port=70000)

    def test_invalid_log_level(self):
        """Test that invalid log level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid log level"):
            APIModel(log_level="invalid")

    def test_invalid_graceful_shutdown_timeout(self):
        """Test that non-positive graceful shutdown timeout raises ValueError."""
        with pytest.raises(ValueError, match="graceful shutdown must be positive"):
            APIModel(timeout_graceful_shutdown=0)


class TestPollingAndSanitizeDefaults:
    """냉동고 검증(sign-glitch 대응) 기본값 불변 확인 — 임의 변경 금지."""

    def test_polling_defaults(self):
        config = PollingModel()
        assert config.loadcells_poll_interval == 0.8
        assert config.loadcells_min_request_gap == 0.75
        assert config.io_status_poll_interval == 0.5

    def test_polling_validation(self):
        with pytest.raises(ValueError, match="Poll interval must be positive"):
            PollingModel(loadcells_poll_interval=0.0)
        with pytest.raises(ValueError, match="Min request gap must be non-negative"):
            PollingModel(loadcells_min_request_gap=-1.0)

    def test_sanitize_defaults(self):
        config = SanitizeModel()
        assert config.enabled is True
        assert config.median_filter is False  # opt-in 유지
        assert config.quantize_grams == 5.0
        assert config.relatch_frames == 3
        assert config.magnitude_tolerance_grams == 2.0
        assert config.min_magnitude_grams == 5.0
        assert config.staleness_seconds == 2.0
        assert config.quantize_hysteresis_grams == 1.0

    def test_sanitize_validation(self):
        with pytest.raises(ValueError, match="relatch_frames must be >= 2"):
            SanitizeModel(relatch_frames=1)
        with pytest.raises(ValueError, match="must be non-negative"):
            SanitizeModel(quantize_hysteresis_grams=-1.0)


class TestHealthModel:
    """/health 임계값 설정 — 기본값은 기존 하드코딩 값과 동일해야 한다."""

    def test_health_defaults(self):
        config = HealthModel()
        assert config.loadcell_min_grams == -40000
        assert config.loadcell_max_grams == 40000
        assert config.door_open_error_seconds == 180.0
        assert config.deadbolt_apply_timeout_seconds == 5.0

    def test_invalid_timeouts(self):
        with pytest.raises(ValueError, match="Timeout must be positive"):
            HealthModel(door_open_error_seconds=0.0)
        with pytest.raises(ValueError, match="Timeout must be positive"):
            HealthModel(deadbolt_apply_timeout_seconds=-1.0)


class TestSettingsLoading:
    """Test Settings loading from environment (IO_BOARD__ prefix)."""

    def test_load_default_settings(self, clean_env):
        """Test loading configuration with defaults."""
        settings = Settings()
        assert settings.serial.port == DEFAULT_SERIAL_PORT
        assert settings.serial.baudrate == 38400
        assert settings.api.host == "0.0.0.0"
        assert settings.api.port == 8000
        assert settings.polling.loadcells_poll_interval == 0.8
        assert settings.polling.loadcells_min_request_gap == 0.75
        assert settings.sanitize.quantize_grams == 5.0
        assert settings.health.loadcell_max_grams == 40000

    def test_load_settings_from_env(self, clean_env):
        """Test loading configuration from environment variables."""
        clean_env.setenv("IO_BOARD__SERIAL__PORT", "COM5")
        clean_env.setenv("IO_BOARD__SERIAL__BAUDRATE", "115200")
        clean_env.setenv("IO_BOARD__API__HOST", "127.0.0.1")
        clean_env.setenv("IO_BOARD__API__PORT", "9000")
        clean_env.setenv("IO_BOARD__HEALTH__DOOR_OPEN_ERROR_SECONDS", "300")

        settings = Settings()
        assert settings.serial.port == "COM5"
        assert settings.serial.baudrate == 115200
        assert settings.api.host == "127.0.0.1"
        assert settings.api.port == 9000
        assert settings.health.door_open_error_seconds == 300.0

    def test_load_settings_partial_env(self, clean_env):
        """Test loading with some env vars set."""
        clean_env.setenv("IO_BOARD__SERIAL__PORT", "/dev/ttyUSB7")

        settings = Settings()
        assert settings.serial.port == "/dev/ttyUSB7"
        assert settings.serial.baudrate == 38400  # Default

    def test_invalid_env_value_rejected(self, clean_env):
        """Test that invalid env values fail validation at load time."""
        clean_env.setenv("IO_BOARD__API__PORT", "70000")

        with pytest.raises(ValueError, match="Port must be between"):
            Settings()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
