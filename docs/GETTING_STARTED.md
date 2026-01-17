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
## Usage Guide and Testing

### Quickstart
1) Install dependencies: `pip install -r requirements.txt`
2) Export env if needed (Windows example):
   - `set IO_BOARD_PORT=COM3`
   - `set IO_BOARD_API_PORT=8000`
3) Run service: `python src/main.py`
4) Call endpoints with curl/httpie or open browser for REST.

### Common REST Calls
- Initialize board: `curl -X POST http://localhost:8000/init`
- Calibrate (shelves empty): `curl -X POST http://localhost:8000/calibrate`
- Set manufacturing number: `curl -X POST http://localhost:8000/manufacturing_number -H "Content-Type: application/json" -d "{\"manufacturing_number\":\"P1234567890\"}"`
- Control deadbolt: `curl -X POST http://localhost:8000/deadbolt -H "Content-Type: application/json" -d "{\"state\":\"OPEN\"}"`
- Get loadcells: `curl http://localhost:8000/loadcells`
- Get door/deadbolt status: `curl http://localhost:8000/status`
- Clear errors: `curl -X DELETE http://localhost:8000/errors`
- Reboot: `curl -X POST http://localhost:8000/reboot`

### Streaming
- Legacy (deprecated): `curl -N http://localhost:8000/stream/loadcells`
  - Emits `event: update` with `{loadcells:[...]} ` at `IO_BOARD_STREAM_INTERVAL` seconds.
- Unified SSE examples:
  - Loadcells only: `curl -N "http://localhost:8000/sse?streams=loadcells&loadcell_interval=0.5"`
  - Loadcells + doors: `curl -N "http://localhost:8000/sse?streams=loadcells,doors&loadcell_interval=0.2&door_interval=1.0"`
  - With filtering: `curl -N "http://localhost:8000/sse?streams=loadcells&filter_method=exponential&filter_alpha=0.3"`
  - Threshold detection: `curl -N "http://localhost:8000/sse?streams=loadcells&threshold=10.0&threshold_scope=filtered"`
  - Per-loadcell thresholds: `curl -N "http://localhost:8000/sse?streams=loadcells&threshold=1,2,3,4,5,6,7,8,9,10&threshold_scope=raw"`

Event names: `loadcell.update`, `loadcell.change`, `loadcell.uncertainty`, `door.update`, `error`.

### Data Formats and Ranges
- Loadcell strings: `+/-` + five digits; errors `EEEEEE` (no comms) or `VVVVVV` (range). Hardware spec range -40000..+40000 (grams).
- Door/deadbolt strings: 6 chars (`CLOSED`, `OPENED`, `LOCKED`, etc.).
- Manufacturing ID: 11 ASCII characters.
- Error history: 4 entries, codes such as DB01 (unlock fail), DB02 (lock fail), LC01–LC10 (loadcell comms/range), or `0000`.

### Filtering and Thresholds
- Methods: `none`, `exponential(alpha)`, `kalman(q,r)` per loadcell.
- Thresholds: single value broadcast to all 10 or comma list of 10. Scope: `raw` compares unfiltered numeric values; `filtered` uses smoothed values.
- Uncertainty: any `EEEEEE`/`VVVVVV` or parse failure triggers `loadcell.uncertainty`; IOBoardError triggers uncertainty for all indices and an `error` event.

### Testing
- Reference: [TESTING.md](TESTING.md) for setup and pytest commands.
- Key test files (can be run in-place or moved under `tests/` as documented):
  - Protocol: [test_protocol_standalone.py](test_protocol_standalone.py)
  - Config: [test_config_standalone.py](test_config_standalone.py)
  - SSE filters/detector: [test_sse_feature.py](test_sse_feature.py)
- Typical commands:
  - `pytest test_protocol_standalone.py -v`
  - `pytest test_config_standalone.py -v`
  - `python test_sse_feature.py`
- For coverage (if moved to `tests/`): `pytest --cov=src.io_board --cov-report=html tests/`
