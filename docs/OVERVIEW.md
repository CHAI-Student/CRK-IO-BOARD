## IO Board Control Service Overview

Purpose: provide a FastAPI REST + SSE layer over the IO Board hardware (loadcells, door/deadbolt control) with binary serial protocol handling and structured logging.

### Architecture at a Glance
- Entry: process starts via [src/main.py](src/main.py); loads env config, sets up structured logging, configures serial, then runs FastAPI server.
- API layer: [src/io_board/api.py](src/io_board/api.py) exposes REST endpoints and streaming `/sse` plus legacy `/stream/loadcells`, applies validation, error mapping, correlation IDs, and performance logging.
- Command layer: [src/io_board/commands.py](src/io_board/commands.py) houses high-level operations (init, door/deadbolt control, calibration, product ID, error clear, reboot, data fetch) and wraps protocol + serial.
- Protocol layer: [src/io_board/protocol.py](src/io_board/protocol.py) defines the binary frame (STX, CMD, SUBCMD, DATA, ETX, checksum XOR) and build/parse helpers.
- Serial layer: [src/io_board/serial_io.py](src/io_board/serial_io.py) performs async serial I/O with mutex, timeouts, retries, and categorized SerialCommunicationError codes.
- Types/models: [src/io_board/io_types.py](src/io_board/io_types.py) contains enums, TypedDicts, and Pydantic models for REST/SSE payloads.
- Filters/events: [src/io_board/filters.py](src/io_board/filters.py) and [src/io_board/events.py](src/io_board/events.py) implement loadcell smoothing (none/exponential/kalman) and threshold/uncertainty detection for streaming.
- Logging: [src/io_board/logging_config.py](src/io_board/logging_config.py) adds structured logs, correlation IDs, payload hex dumps, and performance timing.

### Data Flow
1) REST/SSE request enters FastAPI middleware → correlation ID is set → PerformanceLogger times handler.
2) Handler invokes command function → protocol `build_request` creates frame → serial `fetch` sends/receives with retries/timeouts → protocol `parse_response` validates checksum and extracts data → command returns dict/enum.
3) API serializes Pydantic responses or SSE events; errors are mapped to standardized codes.
4) Streaming `/sse` multiplexes polling tasks (loadcells, doors), applies filters and threshold detection, and emits `loadcell.update`, `loadcell.change`, `loadcell.uncertainty`, `door.update`, `error` events; legacy `/stream/loadcells` streams raw updates only.

### Key Responsibilities by Module
- `api.py`: request validation, SSE orchestration, legacy compatibility, error handlers, uvicorn startup helper.
- `commands.py`: business logic wrappers over protocol/serial, maps responses to friendly shapes.
- `protocol.py`: Construct-based schema for all MC/RQ commands, checksum handling, error surfacing.
- `serial_io.py`: connection management, async timeouts, exponential backoff retries, payload logging.
- `filters.py`/`events.py`: smoothing strategies, per-loadcell state, threshold comparison in raw/filtered scopes, uncertainty detection for error codes (`EEEEEE`/`VVVVVV`) or parse failures.
- `config.py`: env-driven validated settings for serial and API.
- `logging_config.py`: structured formatter, correlation ID filter, performance context manager.

### Components and Concepts
- Commands: MC (PD/DC/LZ/WP/EZ/RT) and RQ (MI/IW/ID/ER) mapped to frame DATA per protocol.
- Data formats: loadcells as 10×6-char strings (signed five digits or error codes), door/deadbolt as 6-char strings, manufacturing ID as 11-char ASCII, errors as 4-char codes.
- Filtering: `none`, `exponential(alpha)`, `kalman(q,r)`; thresholds either single broadcast or 10-per-loadcell; scope raw vs filtered.
- Error taxonomy: configuration (E1xxx), serial (E2xxx), protocol (E3xxx), validation (E4xxx), device (E5xxx), internal (E9xxx/unknown).

### What’s Deprecated
- Legacy SSE endpoint `/stream/loadcells` remains available but is superseded by `/sse` with richer filtering and event types. New clients should migrate to `/sse`.

### Hardware References
- Authoritative hardware/protocol tables live in CSVs: [specs/코맨드_요청_및_응답.csv](specs/%EC%BD%94%EB%A7%A8%EB%93%9C_%EC%9A%94%EC%B2%AD_%EB%B0%8F_%EC%9D%91%EB%8B%B5.csv), [specs/코맨드_종류.csv](specs/%EC%BD%94%EB%A7%A8%EB%93%9C_%EC%A2%85%EB%A5%98.csv), [specs/통신사양서.csv](specs/%ED%86%B5%EC%8B%A0%EC%82%AC%EC%96%91%EC%84%9C.csv). Code-level protocol matches these unless noted otherwise.
