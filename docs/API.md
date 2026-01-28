## REST and SSE API Reference

Authoritative source: [src/io_board/api.py](src/io_board/api.py). Legacy and current endpoints are listed; OpenAPI generation is not present in this repo.

### REST Endpoints

| Method | Path | Description | Request Body | Success Response | Errors |
| --- | --- | --- | --- | --- | --- |
| POST | /init | Initialize IO Board after power-on/reset. | none | 200 SuccessResponse | 500 StandardErrorResponse |
| POST | /deadbolt | Control door deadbolt (OPEN/CLOSE). | DeadboltRequest `{ state: OPEN|CLOSE }` | 200 DeadboltResponse `{ state }` (reflects sensor after command) | 500 StandardErrorResponse |
| POST | /calibrate | Calibrate all loadcells (device unloaded). | none | 200 SuccessResponse | 500 StandardErrorResponse |
| POST | /manufacturing_number | Set 11-char manufacturing/product ID. | ManufacturingNumberRequest `{ manufacturing_number }` | 200 ManufacturingNumberResponse (echo) | 422 validation failure; 500 StandardErrorResponse |
| DELETE | /errors | Clear device error log. | none | 200 SuccessResponse | 500 StandardErrorResponse |
| POST | /reboot | Hard reboot via relay (device may not reply). | none | 200 SuccessResponse | 500 StandardErrorResponse |
| GET | /product_info | Get product ID and SW version. | none | 200 ProductInfoResponse `{ product_id, sw_version }` | 500 StandardErrorResponse |
| GET | /loadcells | Get current loadcell readings (10×6-char strings). | none | 200 LoadCellsResponse `{ loadcells: [str x10] }` | 500 StandardErrorResponse |
| GET | /status | Get door and deadbolt sensor states (6-char strings). | none | 200 IOStatusResponse `{ door, deadbolt }` | 500 StandardErrorResponse |
| GET | /errors | Get error history (up to 4 codes). | none | 200 ErrorListResponse `{ errors: [{code}] }` | 500 StandardErrorResponse |

### Streaming (SSE)

#### Legacy (deprecated)
- Path: `/stream/loadcells`
- Behavior: streams `event: update` with `{ "loadcells": [str x10] }` every `app.state.stream_interval` (from API config). Emits `error` events on failures; continues unless client disconnects.
- Status: marked deprecated; use `/sse` instead.

#### Unified SSE
- Path: `/sse`
- Event types: `loadcell.update`, `loadcell.change`, `loadcell.uncertainty`, `door.update`, `error`.
- Wire format: `text/event-stream` with `event: <name>` and `data: <json>` per SSE standard.

**Query Parameters**

| Name | Type/Range | Default | Description |
| --- | --- | --- | --- |
| streams | string (comma list) | required | `loadcells`, `doors`, or both. Rejects empty/unknown values. |
| filter_method | enum | none | `none`, `exponential`, `kalman`; applied per loadcell. |
| filter_alpha | float 0–1 | 0.2 | EMA alpha (lower = smoother). |
| filter_q | float >0 | 0.001 | Kalman Q (process noise). |
| filter_r | float >0 | 1.0 | Kalman R (measurement noise). |
| threshold | string | "0.0" | Single float or 10 comma-separated floats for change detection. Broadcast if single value. |
| threshold_scope | enum | filtered | `raw` or `filtered` comparison basis. |

**Event Payloads (summaries)**
- `loadcell.update`: `{ timestamp, raw_values[10], filtered_values[10], filter_method }`
- `loadcell.change`: `{ timestamp, changed_indices[], old_values[], new_values[], deltas[], threshold (number or [10]), threshold_scope }`
- `loadcell.uncertainty`: `{ timestamp, affected_indices[], reason(error_state|io_board_failure), details }`
- `door.update`: `{ timestamp, door, deadbolt }` (6-char strings)
- `error`: `{ stream: loadcells|doors, error_code, message, details }`

**Validation Errors (422)**
- Missing streams: `E4002`
- Invalid stream name: `E4003`
- Non-numeric threshold: `E4004`
- Invalid threshold list values: `E4005`
- Wrong threshold count (not 1 or 10): `E4006`

**Runtime Error Behavior**
- Loadcell stream IOBoardError → resets filters, emits `loadcell.uncertainty` for all indices plus `error` event with device error payload.
- Door stream IOBoardError → emits `error` event; stream continues.
- Unexpected exceptions map to `E9002` (loadcells) / `E9003` (doors) `error` events.

### Models (selected)
- SuccessResponse `{ success: bool, message: str }`
- StandardErrorResponse `{ error_code, message, details }`
- Loadcell readings: 6-char strings; error codes `EEEEEE` (no comms) or `VVVVVV` (out of range).
- Door/deadbolt readings: 6-char strings such as `CLOSED`, `OPENED`, `ERROR_`.
- Manufacturing number: 11-char alphanumeric enforced by validation.
