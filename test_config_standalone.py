"""
Unit tests for configuration management.

INSTALLATION: Move to tests/test_config.py after creating tests directory.
"""

import os
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from io_board.config import (
    SerialConfig,
    APIConfig,
    Config,
    load_config,
)


class TestSerialConfig:
    """Test SerialConfig validation."""
    
    def test_valid_serial_config(self):
        """Test creating valid serial configuration."""
        config = SerialConfig(
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
    
    def test_invalid_baudrate(self):
        """Test that invalid baudrate raises ValueError."""
        with pytest.raises(ValueError, match="Baudrate must be positive"):
            SerialConfig(
                port="COM3",
                baudrate=-1,
                header_timeout=0.5,
                body_timeout=2.0,
                checksum_timeout=0.5,
                max_retries=3,
                initial_retry_delay=0.1,
                retry_backoff_multiplier=2.0,
            )
    
    def test_invalid_timeout(self):
        """Test that invalid timeout raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            SerialConfig(
                port="COM3",
                baudrate=38400,
                header_timeout=-0.5,
                body_timeout=2.0,
                checksum_timeout=0.5,
                max_retries=3,
                initial_retry_delay=0.1,
                retry_backoff_multiplier=2.0,
            )
    
    def test_invalid_max_retries(self):
        """Test that invalid max_retries raises ValueError."""
        with pytest.raises(ValueError, match="Max retries must be at least 1"):
            SerialConfig(
                port="COM3",
                baudrate=38400,
                header_timeout=0.5,
                body_timeout=2.0,
                checksum_timeout=0.5,
                max_retries=0,
                initial_retry_delay=0.1,
                retry_backoff_multiplier=2.0,
            )
    
    def test_invalid_backoff_multiplier(self):
        """Test that invalid backoff multiplier raises ValueError."""
        with pytest.raises(ValueError, match="backoff multiplier must be"):
            SerialConfig(
                port="COM3",
                baudrate=38400,
                header_timeout=0.5,
                body_timeout=2.0,
                checksum_timeout=0.5,
                max_retries=3,
                initial_retry_delay=0.1,
                retry_backoff_multiplier=0.5,
            )


class TestAPIConfig:
    """Test APIConfig validation."""
    
    def test_valid_api_config(self):
        """Test creating valid API configuration."""
        config = APIConfig(
            host="0.0.0.0",
            port=8000,
            log_level="info",
            stream_interval=0.5,
        )
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.log_level == "info"
    
    def test_invalid_port_too_low(self):
        """Test that port < 1 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between"):
            APIConfig(
                host="0.0.0.0",
                port=0,
                log_level="info",
                stream_interval=0.5,
            )
    
    def test_invalid_port_too_high(self):
        """Test that port > 65535 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between"):
            APIConfig(
                host="0.0.0.0",
                port=70000,
                log_level="info",
                stream_interval=0.5,
            )
    
    def test_invalid_log_level(self):
        """Test that invalid log level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid log level"):
            APIConfig(
                host="0.0.0.0",
                port=8000,
                log_level="invalid",
                stream_interval=0.5,
            )
    
    def test_invalid_stream_interval(self):
        """Test that invalid stream interval raises ValueError."""
        with pytest.raises(ValueError, match="Stream interval must be positive"):
            APIConfig(
                host="0.0.0.0",
                port=8000,
                log_level="info",
                stream_interval=-1.0,
            )


class TestConfigLoading:
    """Test configuration loading from environment."""
    
    def test_load_default_config(self):
        """Test loading configuration with defaults."""
        # Clear relevant env vars
        env_vars = [
            "IO_BOARD_PORT",
            "IO_BOARD_BAUDRATE",
            "IO_BOARD_API_HOST",
            "IO_BOARD_API_PORT",
        ]
        old_values = {}
        for var in env_vars:
            old_values[var] = os.environ.pop(var, None)
        
        try:
            config = load_config()
            assert config.serial.port == "COM3"
            assert config.serial.baudrate == 38400
            assert config.api.host == "0.0.0.0"
            assert config.api.port == 8000
        finally:
            # Restore env vars
            for var, value in old_values.items():
                if value is not None:
                    os.environ[var] = value
    
    def test_load_config_from_env(self):
        """Test loading configuration from environment variables."""
        # Set env vars
        os.environ["IO_BOARD_PORT"] = "COM5"
        os.environ["IO_BOARD_BAUDRATE"] = "115200"
        os.environ["IO_BOARD_API_HOST"] = "127.0.0.1"
        os.environ["IO_BOARD_API_PORT"] = "9000"
        
        try:
            config = load_config()
            assert config.serial.port == "COM5"
            assert config.serial.baudrate == 115200
            assert config.api.host == "127.0.0.1"
            assert config.api.port == 9000
        finally:
            # Clean up
            del os.environ["IO_BOARD_PORT"]
            del os.environ["IO_BOARD_BAUDRATE"]
            del os.environ["IO_BOARD_API_HOST"]
            del os.environ["IO_BOARD_API_PORT"]
    
    def test_load_config_partial_env(self):
        """Test loading with some env vars set."""
        os.environ["IO_BOARD_PORT"] = "/dev/ttyUSB0"
        
        try:
            config = load_config()
            assert config.serial.port == "/dev/ttyUSB0"
            assert config.serial.baudrate == 38400  # Default
        finally:
            del os.environ["IO_BOARD_PORT"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
