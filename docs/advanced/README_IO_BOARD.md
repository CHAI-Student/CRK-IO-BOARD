# IO Board Control Service

Enterprise-grade REST API service for controlling IO Board devices with loadcells, door locks, and sensors.

## Features

- ✅ **Type-Safe**: Full type hints with Pydantic models
- ✅ **Structured Logging**: Correlation IDs and performance metrics
- ✅ **Configuration Management**: Environment-based configuration with validation
- ✅ **Error Handling**: Custom exception hierarchy with error codes
- ✅ **Retry Logic**: Exponential backoff for transient failures
- ✅ **API Documentation**: Auto-generated OpenAPI/Swagger docs
- ✅ **Real-time Streaming**: Server-Sent Events for loadcell data
- ✅ **Comprehensive Tests**: Unit tests for protocol and commands

## Architecture

```
src/io_board/
├── config.py           # Configuration management
├── exceptions.py       # Custom exception hierarchy
├── types.py            # Type definitions and Pydantic models
├── logging_config.py   # Structured logging setup
├── protocol.py         # Binary protocol implementation
├── serial_io.py        # Serial communication layer
├── commands.py         # High-level command interface
├── api.py              # FastAPI REST endpoints
└── main.py             # Application entry point
```

## Installation

### Dependencies

```bash
pip install fastapi uvicorn pydantic pyserial pyserial-asyncio construct
```

### Development Dependencies

```bash
pip install pytest pytest-asyncio pytest-cov
```

## Configuration

All configuration is done via environment variables:

### Serial Configuration

- `IO_BOARD_PORT` - Serial port path (default: `COM3`)
- `IO_BOARD_BAUDRATE` - Serial baudrate (default: `38400`)
- `IO_BOARD_HEADER_TIMEOUT` - Header read timeout in seconds (default: `0.5`)
- `IO_BOARD_BODY_TIMEOUT` - Body read timeout in seconds (default: `2.0`)
- `IO_BOARD_CHECKSUM_TIMEOUT` - Checksum read timeout in seconds (default: `0.5`)
- `IO_BOARD_MAX_RETRIES` - Maximum retry attempts (default: `3`)
- `IO_BOARD_INITIAL_RETRY_DELAY` - Initial retry delay in seconds (default: `0.1`)
- `IO_BOARD_RETRY_BACKOFF` - Retry backoff multiplier (default: `2.0`)

### API Configuration

- `IO_BOARD_API_HOST` - API server host (default: `0.0.0.0`)
- `IO_BOARD_API_PORT` - API server port (default: `8000`)
- `IO_BOARD_API_LOG_LEVEL` - Log level (default: `info`)
- `IO_BOARD_STREAM_INTERVAL` - SSE stream interval in seconds (default: `0.5`)

## Usage

### Starting the Service

```bash
# Windows
set IO_BOARD_PORT=COM3
python src/io_board/main.py

# Linux/Mac
export IO_BOARD_PORT=/dev/ttyUSB0
python src/io_board/main.py
```

### API Endpoints

The service provides the following REST API endpoints:

#### Device Management

- `POST /init` - Initialize IO Board device
- `POST /calibrate` - Calibrate loadcell sensors
- `POST /manufacturing_number` - Set manufacturing/product ID
- `DELETE /errors` - Clear error log
- `POST /reboot` - Reboot device

#### Door Control

- `POST /deadbolt` - Control door deadbolt (OPEN/CLOSE)

#### Sensors

- `GET /loadcells` - Get current loadcell readings
- `GET /status` - Get door and deadbolt status
- `GET /stream/loadcells` - SSE stream of loadcell data

#### Device Information

- `GET /product_info` - Get product ID and software version
- `GET /errors` - Get error history

### API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Example Requests

#### Initialize Device

```bash
curl -X POST http://localhost:8000/init
```

#### Control Deadbolt

```bash
curl -X POST http://localhost:8000/deadbolt \
  -H "Content-Type: application/json" \
  -d '{"state": "OPEN"}'
```

#### Get Loadcell Readings

```bash
curl http://localhost:8000/loadcells
```

#### Stream Loadcell Data

```bash
curl -N http://localhost:8000/stream/loadcells
```

## Error Handling

All errors follow a standard format:

```json
{
  "error_code": "E2001",
  "message": "Serial port not found",
  "details": {
    "port": "COM3"
  }
}
```

### Error Code Categories

- `E1xxx` - Configuration errors
- `E2xxx` - Serial communication errors
- `E3xxx` - Protocol errors
- `E4xxx` - Validation errors
- `E5xxx` - Device errors
- `E9xxx` - Internal errors

## Logging

The service uses structured logging with correlation IDs:

```
[2026-01-17 12:00:00] [INFO] [abc-123-def] [io_board.api] Request started: method=POST path=/init
[2026-01-17 12:00:00] [DEBUG] [abc-123-def] [io_board.protocol] Building request: command=MC subcommand=PD
[2026-01-17 12:00:00] [DEBUG] [abc-123-def] [io_board.serial_io] TX request: 02 4D 43 50 44 03 0E (7 bytes)
[2026-01-17 12:00:01] [DEBUG] [abc-123-def] [io_board.serial_io] RX response: 02 4D 43 50 44 03 0E (7 bytes)
[2026-01-17 12:00:01] [INFO] [abc-123-def] [io_board.commands] Completed command in 45.23ms cmd=MCPD
[2026-01-17 12:00:01] [INFO] [abc-123-def] [io_board.api] Request completed: status=200
```

## Testing

See [TESTING.md](TESTING.md) for complete testing guide.

### Quick Start

```bash
# Run protocol tests
python test_protocol_standalone.py

# Run config tests
python test_config_standalone.py

# Run with pytest (after setting up tests/ directory)
pytest tests/ -v
```

## Protocol Details

### Binary Frame Structure

```
[STX 0x02][CMD 2B][SUBCMD 2B][DATA VAR][ETX 0x03][CHECKSUM 1B]
```

### Commands

**Management Control (MC)**:
- `PD` - Initialize board
- `DC` - Door control (OPEN/CLOSE)
- `LZ` - Calibrate sensors
- `WP` - Write product ID (11 chars)
- `EZ` - Clear error log
- `RT` - Reboot device

**Request (RQ)**:
- `MI` - Manufacturing info
- `IW` - Loadcell readings (10 × 6 chars)
- `ID` - IO status (door + deadbolt)
- `ER` - Error list (4 × 4 chars)

### Checksum

XOR of all bytes between STX (exclusive) and ETX (exclusive).

## Migration from v1.x

### Breaking Changes

1. **Configuration**: Now uses environment variables instead of hardcoded values
2. **Error Responses**: Changed from `{"msg": "..."}` to structured error format
3. **Endpoint Changes**: `/door` renamed to `/deadbolt`
4. **Imports**: Module structure changed - update import paths

### Migration Steps

1. Set environment variables for configuration
2. Update error handling to use new error format
3. Update endpoint paths in client code
4. Test with new API

## Contributing

### Code Style

- Follow PEP 8
- Use type hints for all functions
- Add comprehensive docstrings
- Keep functions focused and testable

### Pull Request Process

1. Update tests for new functionality
2. Ensure all tests pass
3. Update documentation
4. Add entry to CHANGELOG

## License

[Your License Here]

## Support

For issues and questions, please open a GitHub issue.
