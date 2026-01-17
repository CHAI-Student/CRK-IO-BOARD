## Binary Protocol and Hardware Reference

Sources: [src/io_board/protocol.py](src/io_board/protocol.py), [src/io_board/io_types.py](src/io_board/io_types.py), [specs/코맨드_요청_및_응답.csv](specs/%EC%BD%94%EB%A7%A8%EB%93%9C_%EC%9A%94%EC%B2%AD_%EB%B0%8F_%EC%9D%91%EB%8B%B5.csv), [specs/코맨드_종류.csv](specs/%EC%BD%94%EB%A7%A8%EB%93%9C_%EC%A2%85%EB%A5%98.csv), [specs/통신사양서.csv](specs/%ED%86%B5%EC%8B%A0%EC%82%AC%EC%96%91%EC%84%9C.csv).

### Physical/Link Layer
- Interface: RS-232C async, 38,400 bps, 8 data bits, no parity, 1 stop bit (8N1).
- Timing: start/stop bits per standard; device may toggle deadbolt briefly on init per CSV.

### Frame Layout
- Bytes: `[STX][CMD][SUBCMD][DATA...][ETX][LRC]`
- STX: 0x02; ETX: 0x03.
- CMD/SUBCMD: 2 ASCII chars each.
- DATA: command-specific, see tables.
- LRC/Checksum: XOR of all bytes between STX (exclusive) and ETX (exclusive).

### Command Matrix (MC management/control)

| CMD | SUBCMD | Meaning | DATA (tx/rx) | Notes |
| --- | --- | --- | --- | --- |
| MC | PD | Initialize | none/none | Sent at power-on; device may pulse deadbolt 0.5s for init. |
| MC | DC | Door/deadbolt control | `DOOR` 1 byte (`O` or `C`) / same echoed | Used for deadbolt open/close; RS232 spec notes O=open 0V, C=close. |
| MC | LZ | Calibrate loadcells | none/none | Forces zeroing all loadcells. |
| MC | WP | Write manufacturing ID | 11 ASCII (e.g., `P1234567890`) / echoed | Stored on board. |
| MC | EZ | Clear error history | none/none | Clears 4-slot error log. |
| MC | RT | Reset via relay | none/none | Power-reset PC and SMPS (fridge excluded) per spec note. |

### Request Matrix (RQ data queries)

| CMD | SUBCMD | Meaning | Response DATA | Notes |
| --- | --- | --- | --- | --- |
| RQ | MI | Manufacturing info | PRODUCT_ID (11 ASCII) + SW_VERSION (2 ASCII) | Sent at power-on by host per CSV. |
| RQ | IW | Loadcell weights | 10 readings × 6 ASCII chars | Range -40000..+40000 per spec; error codes `EEEEEE` (no comms) / `VVVVVV` (out of range). |
| RQ | ID | IO status | DOOR (6 ASCII) + DEADBOLT (6 ASCII) | Values like `CLOSED`/`OPENED`; deadbolt sensed by magnet. |
| RQ | ER | Error history | 4 error codes × 4 ASCII | Codes include DB01 (open fail), DB02 (close fail), LC01–LC10 (loadcell comms/range), `0000` for empty; FIFO of last four. |

### Field Formats
- Manufacturing/product ID: 11 ASCII characters (e.g., `P1234567890`).
- Loadcell reading: sign + five digits, e.g., `+01234`, `-40000`; errors `EEEEEE`, `VVVVVV`; practical range 0–40000 g in spec though code allows larger format.
- Door/deadbolt state: 6-char strings, typically `CLOSED`, `OPENED`, `LOCKED`/`OPENED` per CSV; code treats as opaque 6-char.
- Errors: 4-char codes; empty slots `0000`.

### Checksums and Validation
- Builder: `build_request()` assembles Construct frame and XOR checksum.
- Parser: `parse_response()` validates STX/ETX and checksum; errors surface as `ErrorCode.PROTOCOL_CHECKSUM_MISMATCH`, `PROTOCOL_MALFORMED_DATA`, or `PROTOCOL_PARSE_FAILED` with hex context.

### Mismatches/Notes
- Code uses LRC term “checksum” as XOR; matches CSV.
- OpenAPI file is absent; rely on this spec plus source.
- Loadcell value clamp/formatting for filters uses +/- five digits; aligns with hardware range.

### Error Code Meanings (device level from CSV)
- DB01: command to unlock but remains locked.
- DB02: command to lock but remains unlocked.
- LC01–LC10: loadcell comms failure or weight range exceeded per sensor.
- Additional device codes may be vendor-specific; `0000` means no error.

### Reference Implementation Pointers
- Frame schemas: Request/Response structs in [src/io_board/protocol.py](src/io_board/protocol.py).
- Command enums and payload types: [src/io_board/io_types.py](src/io_board/io_types.py).
- High-level command usage: [src/io_board/commands.py](src/io_board/commands.py).
- Filtering/formatting of loadcells for downstream SSE: [src/io_board/events.py](src/io_board/events.py) and [src/io_board/filters.py](src/io_board/filters.py).
