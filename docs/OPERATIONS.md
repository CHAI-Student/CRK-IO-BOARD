## Operations, Configuration, and Logging Runbook

### How to Run
- Install deps: `pip install -r requirements.txt` (or `requirements.dev.txt` for tests).
- Start service (Windows example): `python src/main.py` (launches FastAPI with uvicorn via `serve_api`).
- API listens on `host`/`port` from config; browse `/docs` if generated at runtime or hit REST endpoints directly.

### Configuration (env-driven)
Source: [src/io_board/config.py](src/io_board/config.py). All values validated at init.

| Env Var | Default | Purpose |
| --- | --- | --- |
| IO_BOARD_PORT | COM3 | Serial port path. |
| IO_BOARD_BAUDRATE | 38400 | Baud rate (must be >0). |
| IO_BOARD_HEADER_TIMEOUT | 0.5 | Timeout (s) for STX read. |
| IO_BOARD_BODY_TIMEOUT | 2.0 | Timeout (s) for body through ETX. |
| IO_BOARD_CHECKSUM_TIMEOUT | 0.5 | Timeout (s) for checksum byte. |
| IO_BOARD_MAX_RETRIES | 3 | Retry attempts for serial fetch. |
| IO_BOARD_INITIAL_RETRY_DELAY | 0.1 | First backoff delay (s). |
| IO_BOARD_RETRY_BACKOFF | 2.0 | Backoff multiplier (>=1.0). |
| IO_BOARD_API_HOST | 0.0.0.0 | FastAPI bind host. |
| IO_BOARD_API_PORT | 8000 | FastAPI port (1–65535). |
| IO_BOARD_API_LOG_LEVEL | info | Logging level (critical/error/warning/info/debug/trace). |
| IO_BOARD_STREAM_INTERVAL | 0.5 | Legacy `/stream/loadcells` interval seconds. |

### Logging and Observability
- Structured logger `io_board.*` with correlation ID injected per request (contextvar in [src/io_board/logging_config.py](src/io_board/logging_config.py)).
- Formats: `[timestamp] [LEVEL] [correlation_id] [logger] message`; exceptions appended.
- PerformanceLogger wraps commands/requests and logs completion timing at INFO or error at ERROR.
- Payload hex dumps: `log_payload` logs TX/RX bytes with length at DEBUG.
- Correlation ID helpers: `set_correlation_id`, `get_correlation_id`, `clear_correlation_id`; middleware auto-sets per HTTP request.

### Serial I/O Behavior
- Configured via `configure_serial(config.serial)` at startup.
- Mutex ensures one in-flight serial exchange at a time.
- `_fetch_with_timeout` stages: read STX (header_timeout), read until ETX (body_timeout), read checksum (checksum_timeout).
- Retries: exponential backoff starting at initial_retry_delay up to max_retries; on exhaustion raises `SerialCommunicationError` with codes `E2001`–`E2008`.

### Server Lifecycle
- `serve_api()` sets `app.state.stream_interval` for legacy stream, builds uvicorn `Server` with `force_exit=True`, and serves until cancelled.
- KeyboardInterrupt triggers graceful shutdown logging.

### Operational Tips
- Use DEBUG log level when diagnosing serial/protocol issues to see hex payloads and timing.
- Threshold/filter tuning for `/sse`: start with `filter_method=exponential&filter_alpha=0.2` and `threshold=5.0&threshold_scope=filtered`; adjust per noise level.
- Device reboot via `/reboot` drops power briefly; expect missing replies during the relay action.
- Calibration `/calibrate` should run when shelves are empty; otherwise subsequent readings offset.

### Health Checks
- Lightweight check: GET `/status` for door/deadbolt responses and round-trip time.
- Communication check: GET `/loadcells` and verify 10 readings not `EEEEEE`/`VVVVVV`.
- Error log check: GET `/errors` expecting `0000` entries when clean.
