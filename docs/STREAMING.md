# SSE Endpoint API Reference

## Endpoint Specification

**Method:** `GET`  
**Path:** `/sse`  
**Content-Type:** `text/event-stream`  
**Protocol:** Server-Sent Events (SSE)  

## Request

### URL Format

```
GET /sse?streams=STREAMS[&OPTIONS]
```

### Required Query Parameters

#### `streams` (string, required)

Comma-separated list of data streams to enable.

**Valid values:**
- `loadcells` - Stream loadcell weight readings
- `doors` - Stream door/deadbolt status

**Examples:**
```
streams=loadcells
streams=doors
streams=loadcells,doors
```

**Validation:**
- At least one stream must be specified
- Invalid stream names return `422 Unprocessable Entity`

### Optional Query Parameters

#### Interval Parameters

##### `loadcell_interval` (float, optional)

Polling interval for loadcell data in seconds.

**Default:** `0.5`  
**Range:** `[0.1, 10.0]` (inclusive)  
**Unit:** Seconds  
**Applies to:** `loadcells` stream only  

**Examples:**
```
loadcell_interval=0.1    # 10 Hz - high frequency
loadcell_interval=0.5    # 2 Hz - default
loadcell_interval=2.0    # 0.5 Hz - low frequency
```

**Validation:**
- Must be >= 0.1 (minimum 100ms)
- Must be <= 10.0 (maximum 10 seconds)
- Out-of-range values return `422 Unprocessable Entity`

---

##### `door_interval` (float, optional)

Polling interval for door status in seconds.

**Default:** `1.0`  
**Range:** `[0.1, 10.0]` (inclusive)  
**Unit:** Seconds  
**Applies to:** `doors` stream only  

**Examples:**
```
door_interval=0.5    # Quick response to door changes
door_interval=1.0    # Default - standard access control
door_interval=5.0    # Low-frequency monitoring
```

**Validation:**
- Must be >= 0.1
- Must be <= 10.0

---

#### Filter Parameters

##### `filter_method` (enum, optional)

Filtering algorithm to apply to loadcell values.

**Default:** `none`  
**Valid values:** `none`, `exponential`, `kalman`  
**Applies to:** Loadcell values only  

**Values:**

| Method | Use Case | Characteristics |
|--------|----------|-----------------|
| `none` | Raw data, debugging | No latency, noisy |
| `exponential` | General smoothing | Configurable alpha, low CPU |
| `kalman` | Optimal smoothing | Adaptive, best quality |

**Examples:**
```
filter_method=none
filter_method=exponential
filter_method=kalman
```

---

##### `filter_alpha` (float, optional)

Alpha parameter for exponential smoothing filter.

**Default:** `0.2`  
**Range:** `[0.0, 1.0]` (inclusive)  
**Applies to:** Only when `filter_method=exponential`  
**Ignored when:** `filter_method` is `none` or `kalman`  

**Semantics:**
- `0.0` = Maximum smoothing (heavily weighted toward previous values)
- `0.5` = Balanced (equal weight to new and old)
- `1.0` = No smoothing (raw passthrough)

**Examples:**
```
filter_alpha=0.1    # Heavy smoothing (slow response)
filter_alpha=0.2    # Default (recommended)
filter_alpha=0.5    # Moderate smoothing
filter_alpha=0.9    # Light smoothing (fast response)
```

**Formula:**
```
filtered_value = alpha * new_raw_value + (1 - alpha) * previous_filtered_value
```

---

##### `filter_q` (float, optional)

Process noise covariance (Q) for Kalman filter.

**Default:** `0.001`  
**Range:** `> 0.0` (must be positive)  
**Applies to:** Only when `filter_method=kalman`  
**Ignored when:** `filter_method` is `none` or `exponential`  

**Semantics:**
- Controls how much the true value is assumed to change over time
- Smaller Q = assumes value is more static (more smoothing)
- Larger Q = assumes value changes more freely (less smoothing)

**Typical values:**
```
filter_q=0.0001     # Assume very stable (heavy smoothing)
filter_q=0.001      # Default (recommended for loadcells)
filter_q=0.01       # Assume moderate changes
filter_q=0.1        # Assume significant changes
```

---

##### `filter_r` (float, optional)

Measurement noise covariance (R) for Kalman filter.

**Default:** `1.0`  
**Range:** `> 0.0` (must be positive)  
**Applies to:** Only when `filter_method=kalman`  
**Ignored when:** `filter_method` is `none` or `exponential`  

**Semantics:**
- Controls how much the sensor reading is trusted
- Smaller R = trust sensor more (less filtering)
- Larger R = trust sensor less (more filtering)

**Typical values:**
```
filter_r=0.5    # High-quality sensor (trust it more)
filter_r=1.0    # Default (average quality)
filter_r=2.0    # Lower-quality sensor (trust it less)
filter_r=10.0   # Very noisy sensor (heavy filtering)
```

---

#### Threshold Parameters

##### `threshold` (string, optional)

Change threshold for detecting loadcell value changes.

**Default:** `"0.0"`  
**Format:** 
- Single value: `"5.0"` (broadcast to all 10 loadcells)
- Per-loadcell: `"5.0,10.0,5.0,8.0,5.0,5.0,12.0,5.0,5.0,5.0"` (exactly 10 comma-separated values)

**Applies to:** Loadcell streams only  

**Semantics:**
- Triggers `loadcell.change` event when `|new_value - old_value| > threshold`
- `0.0` (default) means only fire on any non-zero change

**Examples:**

Single value:
```
threshold=0.0     # Any change triggers event
threshold=5.0     # Must change by more than 5 units
threshold=10.0    # Must change by more than 10 units
threshold=50.0    # Only large changes trigger
```

Per-loadcell (10 values, corresponding to loadcells 0-9):
```
threshold=5.0,10.0,5.0,5.0,5.0,5.0,5.0,5.0,5.0,5.0
threshold=1.0,1.0,1.0,1.0,1.0,50.0,50.0,1.0,1.0,1.0
```

**Validation:**
- Must parse as valid floats
- Must be 1 value OR exactly 10 values (else `422`)
- Negative values allowed (but unusual)

---

##### `threshold_scope` (enum, optional)

Which values to apply threshold comparison to.

**Default:** `filtered`  
**Valid values:** `raw`, `filtered`  
**Applies to:** Loadcell streams only  

**Values:**

| Scope | Compare Against | Characteristics |
|-------|-----------------|-----------------|
| `raw` | Raw unfiltered values | Immediate response, prone to noise |
| `filtered` | Filtered values | Stable detection, slight lag from filter |

**Examples:**
```
threshold_scope=raw       # Immediate response to any change
threshold_scope=filtered  # Noise-resistant (recommended)
```

**Recommendation:**
- Use `filtered` with exponential/Kalman filter for noise rejection
- Use `raw` only if sensors are very clean or immediate response required

---

## Response

### HTTP Headers

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Correlation-ID: abc-123-def
Transfer-Encoding: chunked
```

**Key headers:**
- `Content-Type: text/event-stream` - SSE protocol
- `Cache-Control: no-cache` - Prevent caching of stream
- `Connection: keep-alive` - Keep connection open
- `X-Correlation-ID` - Request tracking ID

---

### Response Body

Server-Sent Events format: Each event consists of event name and JSON data.

**Format:**
```
event: <event_name>
data: <json_payload>

```

**Example stream:**
```
event: loadcell.update
data: {"timestamp":"2026-01-17T14:30:45.123456","raw_values":["+12345","+00123",...],"filtered_values":["+12340","+00120",...],"filter_method":"exponential"}

event: loadcell.change
data: {"timestamp":"2026-01-17T14:30:45.234567","changed_indices":[0],"old_values":[12340.0],"new_values":[12350.0],"deltas":[10.0],"threshold":5.0,"threshold_scope":"filtered"}

event: door.update
data: {"timestamp":"2026-01-17T14:30:45.456789","door":"CLOSED","deadbolt":"CLOSED"}

```

---

## Error Responses

### Validation Error (422)

**Status Code:** `422 Unprocessable Entity`

**Cause:** Invalid query parameters

**Response Body:**

```json
{
  "error_code": "E4002",
  "message": "At least one stream must be specified",
  "details": {
    "valid_streams": ["loadcells", "doors"]
  }
}
```

**Common error codes:**

| Code | Reason |
|------|--------|
| `E4002` | No streams specified |
| `E4003` | Invalid stream name(s) |
| `E4004` | Invalid threshold format (not a number) |
| `E4005` | Invalid threshold values (non-numeric values in list) |
| `E4006` | Wrong number of threshold values (not 1 or 10) |

---

### Server Error (500)

**Status Code:** `500 Internal Server Error`

**Cause:** Unexpected server error (rare)

**Ongoing behavior:** Stream continues, sends `error` events (see below)

---

## Streaming Events

### Event: `loadcell.update`

**Emitted:** Every `loadcell_interval` seconds (periodic)  
**When:** `loadcells` in streams AND successful I/O read  

**JSON:**
```json
{
  "timestamp": "2026-01-17T14:30:45.123456",
  "raw_values": [
    "+12345", "+00123", "-00456", "+99999", "+00000",
    "+11111", "+22222", "+33333", "+44444", "+55555"
  ],
  "filtered_values": [
    "+12340", "+00120", "-00450", "+99995", "+00000",
    "+11110", "+22220", "+33330", "+44440", "+55550"
  ],
  "filter_method": "exponential"
}
```

**Fields:**
| Field | Type | Length | Description |
|-------|------|--------|-------------|
| `timestamp` | string | ISO 8601 | Reading timestamp (UTC) |
| `raw_values` | array[10] | 6 chars each | Raw loadcell readings |
| `filtered_values` | array[10] | 6 chars each | Filtered readings |
| `filter_method` | string | - | Filter applied |

---

### Event: `loadcell.change`

**Emitted:** When threshold exceeded (conditional)  
**When:** `loadcells` in streams AND change > threshold  

**JSON:**
```json
{
  "timestamp": "2026-01-17T14:30:45.234567",
  "changed_indices": [0, 3, 7],
  "old_values": [12340.0, 99995.0, 33330.0],
  "new_values": [12350.0, 99985.0, 33340.0],
  "deltas": [10.0, 10.0, 10.0],
  "threshold": 5.0,
  "threshold_scope": "filtered"
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | Detection timestamp (UTC) |
| `changed_indices` | array[n] | Indices of changed loadcells |
| `old_values` | array[n] | Previous values (numerics) |
| `new_values` | array[n] | New values (numerics) |
| `deltas` | array[n] | Absolute change amounts |
| `threshold` | number or array | Threshold value(s) |
| `threshold_scope` | string | `raw` or `filtered` |

---

### Event: `loadcell.uncertainty`

**Emitted:** On sensor error or I/O failure (conditional, **CRITICAL**)  
**When:** `loadcells` in streams AND error detected  

**JSON (Sensor Error):**
```json
{
  "timestamp": "2026-01-17T14:30:45.345678",
  "affected_indices": [5, 8],
  "reason": "error_state",
  "details": {
    "error_values": ["EEEEEE", "VVVVVV"]
  }
}
```

**JSON (I/O Board Failure):**
```json
{
  "timestamp": "2026-01-17T14:30:45.345678",
  "affected_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  "reason": "io_board_failure",
  "details": {
    "error_code": "E2001",
    "message": "Serial communication timeout",
    "details": {}
  }
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | Detection timestamp (UTC) |
| `affected_indices` | array | Loadcells with uncertainty (0-9) |
| `reason` | string | `error_state` or `io_board_failure` |
| `details` | object | Error-specific data |

**⚠️ SECURITY EVENT:** Treat any uncertainty as potential theft/tampering

---

### Event: `door.update`

**Emitted:** Every `door_interval` seconds (periodic)  
**When:** `doors` in streams AND successful I/O read  

**JSON:**
```json
{
  "timestamp": "2026-01-17T14:30:45.456789",
  "door": "CLOSED",
  "deadbolt": "CLOSED"
}
```

**Fields:**
| Field | Type | Length | Description |
|-------|------|--------|-------------|
| `timestamp` | string | ISO 8601 | Reading timestamp (UTC) |
| `door` | string | 6 chars | Door sensor status |
| `deadbolt` | string | 6 chars | Deadbolt sensor status |

---

### Event: `error`

**Emitted:** On stream communication error (conditional)  
**When:** I/O board communication fails  

**JSON:**
```json
{
  "stream": "loadcells",
  "error_code": "E2001",
  "message": "Serial communication timeout",
  "details": {}
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `stream` | string | `loadcells` or `doors` |
| `error_code` | string | Machine-readable error code |
| `message` | string | Human-readable message |
| `details` | object | Additional context |

**Note:** Stream **does not terminate** on error events

---

## Behavior Specifications

### Timing

- **Periodic events** (`loadcell.update`, `door.update`): Emitted at configured intervals
- **Event lag:** ~0-100ms after polling interval trigger
- **Filter initialization:** Filters initialize on first valid reading (zero startup lag)

### Error Handling

- **I/O Board Failure:** 
  - Emits `error` event on first failure
  - Emits `loadcell.uncertainty` with affected_indices=[0-9]
  - Retries polling at normal interval
  - Filter state **automatically reset** on reconnection

- **Sensor Error:** 
  - Emits `loadcell.uncertainty` event
  - Stream continues normally
  - Affected loadcells return error codes in next `loadcell.update`

- **Stream Error:** 
  - Emits `error` event
  - Stream continues
  - Polling resumes at next interval

### Connection Management

- **Client Disconnect:** Server detects and cancels polling tasks
- **Server Shutdown:** All streams terminate gracefully
- **Auto-Reconnect:** EventSource API auto-reconnects (JavaScript)
- **Keep-Alive:** TCP keep-alive prevents connection timeout

### Filter State

- **Initialization:** Starts with first valid reading (no artificial zero)
- **Reset:** Automatically resets on I/O board reconnection
- **Persistence:** Maintained across multiple readings within session
- **Per-Connection:** Each SSE connection has independent filter instances

### Data Consistency

- **Loadcell Values:** Always 10 values per event
- **Array Alignment:** `changed_indices`, `old_values`, `new_values`, `deltas` have matching lengths
- **Timestamps:** All timestamps are UTC ISO 8601
- **JSON:** Valid JSON per RFC 7159

---

## Rate Limiting

- **No explicit rate limiting**
- **Trust interval parameters** (0.1s minimum enforced)
- **Typical rates:** 2-3 events/second with default intervals
- **Peak rates:** ~20 events/second at minimum intervals (0.1s)

---

## OpenAPI Documentation

Access full interactive documentation at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

---

## Examples

### Example 1: Anti-Theft Monitoring
```
GET /sse?streams=loadcells&loadcell_interval=0.1&filter_method=exponential&filter_alpha=0.2&threshold=5.0&threshold_scope=filtered
```
Response: `loadcell.update` every 100ms, `loadcell.change` events on weight changes > 5.0

### Example 2: Door Access Control
```
GET /sse?streams=doors&door_interval=0.5
```
Response: `door.update` every 500ms when door status changes

### Example 3: Combined Monitoring
```
GET /sse?streams=loadcells,doors&loadcell_interval=0.5&door_interval=1.0&filter_method=kalman&filter_q=0.001&filter_r=1.0&threshold=10.0
```
Response: Both streams with Kalman filtering and 10-unit threshold

---

## Testing

### Using curl
```bash
curl -N "http://localhost:8000/sse?streams=loadcells&threshold=10.0"
```

### Using Python
```python
import requests
with requests.get('http://localhost:8000/sse?streams=loadcells', stream=True) as r:
    for line in r.iter_lines():
        print(line.decode())
```

### Using JavaScript
```javascript
const es = new EventSource('http://localhost:8000/sse?streams=loadcells');
es.addEventListener('loadcell.update', (e) => console.log(JSON.parse(e.data)));
```

---

## Version Information

- **API Version:** 2.0.0
- **SSE Protocol:** Standard W3C Server-Sent Events
- **JSON:** RFC 7159
- **Timestamps:** ISO 8601 (UTC)
# SSE Streaming Response Format Specification

## Overview

The `/sse` endpoint returns a **Server-Sent Events (SSE)** stream with configurable event types. Each event is sent with a unique event name allowing clients to listen for specific event types.

## SSE Protocol Format

All events follow the standard SSE protocol:

```
event: <event_name>
data: <json_payload>

```

**Important:** Each message ends with **two newlines** (`\n\n`)

## Event Types and Formats

### 1. `loadcell.update` Event

**Purpose:** Periodic loadcell readings with raw and filtered values

**Emission Interval:** Controlled by `loadcell_interval` query parameter (default: 0.5s)

**Preconditions:**
- `loadcells` must be in `streams` parameter
- Successfully read from I/O board

**JSON Schema:**

```json
{
  "timestamp": "string (ISO 8601 UTC)",
  "raw_values": ["string (6 chars)", "string (6 chars)", ...],
  "filtered_values": ["string (6 chars)", "string (6 chars)", ...],
  "filter_method": "string (none|exponential|kalman)"
}
```

**Field Details:**

| Field | Type | Length | Description |
|-------|------|--------|-------------|
| `timestamp` | string | ISO 8601 | UTC timestamp of reading (e.g., `2026-01-17T14:30:45.123456`) |
| `raw_values` | array | 10 items | Raw 6-character loadcell readings from device |
| `filtered_values` | array | 10 items | Filtered 6-character loadcell readings (after applying filter) |
| `filter_method` | string | N/A | Filter method: `none`, `exponential`, or `kalman` |

**Raw Value Format (6 characters):**
- Format: `[+/-][5 digits]` or error code
- Examples: `+12345`, `-00001`, `+00000`
- Error codes: `EEEEEE` (sensor error), `VVVVVV` (sensor invalid)
- Numeric range: -99999 to +99999

**Real Example:**

```
event: loadcell.update
data: {"timestamp":"2026-01-17T14:30:45.123456","raw_values":["+12345","+00123","-00456","+99999","+00000","+11111","+22222","+33333","+44444","+55555"],"filtered_values":["+12340","+00120","-00450","+99995","+00000","+11110","+22220","+33330","+44440","+55550"],"filter_method":"exponential"}

```

---

### 2. `loadcell.change` Event

**Purpose:** Threshold breach detection - emitted when loadcell change exceeds configured threshold

**Emission Trigger:** When absolute value change > threshold (on raw or filtered scope per config)

**Preconditions:**
- `loadcells` must be in `streams` parameter
- At least one loadcell exceeds configured threshold
- Previous value initialized (not first reading)

**JSON Schema:**

```json
{
  "timestamp": "string (ISO 8601 UTC)",
  "changed_indices": [0, 3, 7],
  "old_values": [12340.0, 99995.0, 33330.0],
  "new_values": [12350.0, 99985.0, 33340.0],
  "deltas": [10.0, 10.0, 10.0],
  "threshold": 5.0,
  "threshold_scope": "string (raw|filtered)"
}
```

**Field Details:**

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 UTC timestamp when change detected |
| `changed_indices` | array | Indices (0-9) of loadcells that exceeded threshold |
| `old_values` | array | Previous numeric values for changed loadcells (floats) |
| `new_values` | array | New numeric values for changed loadcells (floats) |
| `deltas` | array | Absolute change amounts for changed loadcells (floats) |
| `threshold` | number or array | Threshold value(s): single number or array of 10 per-loadcell thresholds |
| `threshold_scope` | string | Whether threshold applies to `raw` or `filtered` values |

**Important:** Array alignment
- `changed_indices`, `old_values`, `new_values`, and `deltas` have **the same length**
- Index 0 of these arrays corresponds to the first changed loadcell
- Use `changed_indices[i]` to map back to original loadcell position

**Threshold Field:**
- If single value provided (broadcast): returns as number
- If per-loadcell values: returns as array of 10 numbers

**Real Example (Single Threshold):**

```
event: loadcell.change
data: {"timestamp":"2026-01-17T14:30:45.234567","changed_indices":[0,3,7],"old_values":[12340.0,99995.0,33330.0],"new_values":[12350.5,99985.1,33340.2],"deltas":[10.5,9.9,10.2],"threshold":5.0,"threshold_scope":"filtered"}

```

**Real Example (Per-Loadcell Thresholds):**

```
event: loadcell.change
data: {"timestamp":"2026-01-17T14:30:45.234567","changed_indices":[0,3],"old_values":[12340.0,99995.0],"new_values":[12355.0,99980.0],"deltas":[15.0,15.0],"threshold":[5.0,10.0,5.0,8.0,5.0,5.0,12.0,5.0,5.0,5.0],"threshold_scope":"filtered"}

```

---

### 3. `loadcell.uncertainty` Event

**Purpose:** Error detection and anti-theft monitoring - emitted when loadcell sensors fail or I/O board communication fails

**🚨 SECURITY EVENT:** Treat any uncertainty as potential theft/tampering

**Emission Trigger:** 
1. Loadcell returns error codes ("EEEEEE" or "VVVVVV")
2. I/O board communication failure (affects all loadcells)
3. Parse failures on valid-looking data

**Preconditions:**
- `loadcells` must be in `streams` parameter
- Uncertainty condition detected

**JSON Schema (Error State):**

```json
{
  "timestamp": "string (ISO 8601 UTC)",
  "affected_indices": [5, 8, 9],
  "reason": "error_state",
  "details": {
    "error_values": ["EEEEEE", "VVVVVV", "EEEEEE"]
  }
}
```

**JSON Schema (I/O Board Failure):**

```json
{
  "timestamp": "string (ISO 8601 UTC)",
  "affected_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  "reason": "io_board_failure",
  "details": {
    "error_code": "E2001",
    "message": "Serial communication timeout",
    "details": {}
  }
}
```

**Field Details:**

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 UTC timestamp when uncertainty detected |
| `affected_indices` | array | Indices (0-9) of loadcells with uncertainty |
| `reason` | string | `error_state` or `io_board_failure` |
| `details` | object | Context: `error_values` for error_state, or error response for io_board_failure |

**Reason Values:**

- `error_state`: Individual loadcell sensor returned error code
  - `details.error_values`: Array of error codes (e.g., `["EEEEEE", "VVVVVV"]`)
  
- `io_board_failure`: I/O board communication error
  - All 10 loadcells marked uncertain (indices 0-9)
  - `details` contains standard IOBoardError response (error_code, message, details)
  - Filter state is **automatically reset** after this event

**Real Example (Sensor Error):**

```
event: loadcell.uncertainty
data: {"timestamp":"2026-01-17T14:30:45.345678","affected_indices":[5,8],"reason":"error_state","details":{"error_values":["EEEEEE","VVVVVV"]}}

```

**Real Example (I/O Board Failure):**

```
event: loadcell.uncertainty
data: {"timestamp":"2026-01-17T14:30:45.345678","affected_indices":[0,1,2,3,4,5,6,7,8,9],"reason":"io_board_failure","details":{"error_code":"E2001","message":"Serial communication timeout","details":{}}}

```

---

### 4. `door.update` Event

**Purpose:** Periodic door and deadbolt status readings

**Emission Interval:** Controlled by `door_interval` query parameter (default: 1.0s)

**Preconditions:**
- `doors` must be in `streams` parameter
- Successfully read from I/O board

**JSON Schema:**

```json
{
  "timestamp": "string (ISO 8601 UTC)",
  "door": "string (6 chars)",
  "deadbolt": "string (6 chars)"
}
```

**Field Details:**

| Field | Type | Length | Description |
|-------|------|--------|-------------|
| `timestamp` | string | ISO 8601 | UTC timestamp of reading |
| `door` | string | 6 chars | Door sensor status |
| `deadbolt` | string | 6 chars | Deadbolt sensor status |

**Sensor Status Values (6 characters):**
- `CLOSED` - Sensor reading: closed/locked
- `OPENED` - Sensor reading: open/unlocked
- `ERROR_` - Sensor error state
- Other implementation-defined values

**Real Example:**

```
event: door.update
data: {"timestamp":"2026-01-17T14:30:45.456789","door":"CLOSED","deadbolt":"CLOSED"}

```

---

### 5. `error` Event

**Purpose:** Stream-level errors (communication failures, processing errors)

**Emission Trigger:**
- I/O board communication error during polling
- Unexpected exception in stream processing

**Preconditions:**
- Any stream enabled
- Error condition encountered

**JSON Schema:**

```json
{
  "stream": "string (loadcells|doors)",
  "error_code": "string",
  "message": "string",
  "details": {}
}
```

**Field Details:**

| Field | Type | Description |
|-------|------|-------------|
| `stream` | string | Which stream failed: `loadcells` or `doors` |
| `error_code` | string | Machine-readable error code (e.g., `E2001`, `E9002`) |
| `message` | string | Human-readable error message |
| `details` | object | Additional context (empty in most cases) |

**Error Codes:**

| Code | Meaning |
|------|---------|
| `E2001` | Serial communication timeout |
| `E2002` | Serial port error |
| `E3001` | Invalid protocol response |
| `E9002` | Unexpected loadcell stream error |
| `E9003` | Unexpected door stream error |

**Note:** Error events do **NOT** terminate the stream - polling continues

**Real Example:**

```
event: error
data: {"stream":"loadcells","error_code":"E2001","message":"Serial communication timeout","details":{}}

```

---

## Client-Side Event Handling

### JavaScript EventSource API

```javascript
const eventSource = new EventSource('http://localhost:8000/sse?streams=loadcells,doors&loadcell_interval=0.5&threshold=10.0');

// Listen for loadcell updates
eventSource.addEventListener('loadcell.update', (event) => {
  const data = JSON.parse(event.data);
  console.log('Filtered values:', data.filtered_values);
});

// Listen for threshold breaches (anti-theft)
eventSource.addEventListener('loadcell.change', (event) => {
  const data = JSON.parse(event.data);
  console.warn('Weight change detected on loadcells:', data.changed_indices);
});

// Listen for sensor errors (CRITICAL ANTI-THEFT)
eventSource.addEventListener('loadcell.uncertainty', (event) => {
  const data = JSON.parse(event.data);
  console.error('SECURITY EVENT - Uncertainty on loadcells:', data.affected_indices);
  if (data.reason === 'io_board_failure') {
    triggerMaintenanceAlert('I/O Board Communication Lost');
  } else {
    triggerAntiTheftAlert(`Sensor Error on Loadcells ${data.affected_indices}`);
  }
});

// Listen for door status
eventSource.addEventListener('door.update', (event) => {
  const data = JSON.parse(event.data);
  console.log('Door:', data.door, 'Deadbolt:', data.deadbolt);
});

// Listen for errors
eventSource.addEventListener('error', (event) => {
  const data = JSON.parse(event.data);
  console.error(`Error on ${data.stream}: ${data.message}`);
});

// Auto-reconnect on connection loss
eventSource.onerror = (error) => {
  console.error('Connection lost, will reconnect...');
  // EventSource automatically reconnects with exponential backoff
};
```

### Python Requests Library

```python
import requests
import json

with requests.get('http://localhost:8000/sse?streams=loadcells&threshold=10.0', stream=True) as response:
    for line in response.iter_lines():
        if not line:
            continue
        
        line_str = line.decode('utf-8')
        
        if line_str.startswith('event:'):
            event_type = line_str.split(':', 1)[1].strip()
        elif line_str.startswith('data:'):
            data_str = line_str.split(':', 1)[1].strip()
            data = json.loads(data_str)
            
            # Process by event type
            if event_type == 'loadcell.update':
                print(f'Filtered: {data["filtered_values"]}')
            elif event_type == 'loadcell.change':
                print(f'⚠️ Change on {data["changed_indices"]}')
            elif event_type == 'loadcell.uncertainty':
                print(f'🚨 SECURITY: {data["reason"]} on {data["affected_indices"]}')
            elif event_type == 'door.update':
                print(f'Door: {data["door"]}')
            elif event_type == 'error':
                print(f'❌ {data["stream"]} error: {data["message"]}')
```

---

## Timestamp Format

All `timestamp` fields use ISO 8601 format with UTC timezone:

```
YYYY-MM-DDTHH:MM:SS.ffffff
```

Examples:
- `2026-01-17T14:30:45.123456` - January 17, 2026 at 2:30:45 PM + microseconds
- `2026-01-17T00:00:00.000000` - Midnight UTC

---

## Error Handling Strategy

### Connection Loss
- **EventSource API:** Automatically reconnects with exponential backoff (no action needed)
- **Manual Reconnection:** Check `readyState` of EventSource object

### Sensor Errors vs. Communication Errors
- **Sensor Error:** `loadcell.uncertainty` event with `reason="error_state"` - check affected loadcells
- **Communication Error:** `error` event OR `loadcell.uncertainty` with `reason="io_board_failure"` - entire system issue

### Filter State Management
- Filter state (for exponential/Kalman) is maintained per connection
- On I/O board failure, filter state is **automatically reset** to prevent stale filtering after reconnection

### Resilience
- Stream never terminates due to errors
- Error events allow graceful degradation and alerting
- Client can decide whether to close connection or continue listening

---

## Performance Considerations

### Event Rate

```
Approximate event rate with default parameters:
- loadcells at 0.5s interval: ~2 events/second
- doors at 1.0s interval: ~1 event/second
- Total: ~3 events/second (baseline)

Additional events:
- loadcell.change: Only on threshold breach (variable)
- loadcell.uncertainty: Only on errors (variable)
- error: Only on communication errors (variable)
```

### Bandwidth

```
Single loadcell.update event: ~800-1000 bytes (JSON overhead)
Single door.update event: ~300-400 bytes
Single loadcell.change event: ~500-800 bytes (depends on count changed)
Single loadcell.uncertainty event: ~400-600 bytes

With defaults: ~4-5 KB/second baseline
```

### Network Settings

- **Keep-Alive:** Enabled (`Connection: keep-alive`)
- **Caching:** Disabled (`Cache-Control: no-cache`)
- **Compression:** May be applied by HTTP layer

---

## Testing Event Streams

### Using `curl`

```bash
# Monitor all events
curl -N "http://localhost:8000/sse?streams=loadcells,doors&loadcell_interval=0.5"

# Monitor only changes (high-frequency threshold testing)
curl -N "http://localhost:8000/sse?streams=loadcells&threshold=1.0"

# Test with filtering
curl -N "http://localhost:8000/sse?streams=loadcells&filter_method=exponential&filter_alpha=0.5&threshold=5.0"
```

### Using `websocat` (SSE simulator)

```bash
# Install: cargo install websocat

# Test connection
websocat "ws://localhost:8000/sse?streams=loadcells" 2>&1 | head -20
```

### Using Browser Console

```javascript
// Open browser DevTools Console
const es = new EventSource('http://localhost:8000/sse?streams=loadcells,doors&threshold=10.0');
es.onmessage = (e) => console.log(e.data);
es.onerror = (e) => console.error('Error:', e);

// Close stream
es.close();
```
# SSE Streaming API - Usage Examples

## Overview

The unified `/sse` endpoint provides real-time Server-Sent Events streaming for loadcell and door status monitoring with configurable filtering and threshold-based change detection.

## Quick Start

### Basic Loadcell Stream

```bash
curl "http://localhost:8000/sse?streams=loadcells"
```

### Basic Door Stream

```bash
curl "http://localhost:8000/sse?streams=doors"
```

### Combined Streams

```bash
curl "http://localhost:8000/sse?streams=loadcells,doors&loadcell_interval=0.2&door_interval=1.0"
```

## Event Types

The `/sse` endpoint emits the following event types:

### `loadcell.update`
Periodic loadcell readings with raw and filtered values.

**Example:**
```
event: loadcell.update
data: {
  "timestamp": "2026-01-17T14:30:45.123456",
  "raw_values": ["+12345", "+00123", "-00456", "+99999", "+00000", "+11111", "+22222", "+33333", "+44444", "+55555"],
  "filtered_values": ["+12340", "+00120", "-00450", "+99995", "+00000", "+11110", "+22220", "+33330", "+44440", "+55550"],
  "filter_method": "exponential"
}
```

### `loadcell.change`
Emitted when loadcell value change exceeds configured threshold.

**Example:**
```
event: loadcell.change
data: {
  "timestamp": "2026-01-17T14:30:45.123456",
  "changed_indices": [0, 3, 7],
  "old_values": [12340.0, 99995.0, 33330.0],
  "new_values": [12350.0, 99985.0, 33340.0],
  "deltas": [10.0, 10.0, 10.0],
  "threshold": 5.0,
  "threshold_scope": "filtered"
}
```

### `loadcell.uncertainty`
Emitted when loadcell encounters error states (anti-theft event).

**Example:**
```
event: loadcell.uncertainty
data: {
  "timestamp": "2026-01-17T14:30:45.123456",
  "affected_indices": [5, 8],
  "reason": "error_state",
  "details": {"error_values": ["EEEEEE", "VVVVVV"]}
}
```

### `door.update`
Periodic door and deadbolt status.

**Example:**
```
event: door.update
data: {
  "timestamp": "2026-01-17T14:30:45.123456",
  "door": "CLOSED",
  "deadbolt": "CLOSED"
}
```

### `error`
Stream-level errors (I/O board communication failures).

**Example:**
```
event: error
data: {
  "stream": "loadcells",
  "error_code": "E2001",
  "message": "Serial communication timeout",
  "details": {}
}
```

## Query Parameters

### Required Parameters

- **`streams`** (required): Comma-separated list of streams to enable
  - Valid values: `loadcells`, `doors`
  - Example: `streams=loadcells,doors`

### Interval Parameters

- **`loadcell_interval`** (optional, default: 0.5)
  - Polling interval for loadcell updates in seconds
  - Range: [0.1, 10.0]
  - Example: `loadcell_interval=0.2`

- **`door_interval`** (optional, default: 1.0)
  - Polling interval for door status updates in seconds
  - Range: [0.1, 10.0]
  - Example: `door_interval=1.5`

### Filter Parameters

- **`filter_method`** (optional, default: `none`)
  - Filtering method for loadcell values
  - Valid values: `none`, `exponential`, `kalman`
  - Example: `filter_method=exponential`

- **`filter_alpha`** (optional, default: 0.2)
  - Alpha parameter for exponential smoothing
  - Range: [0.0, 1.0]
  - 0.0 = maximum smoothing, 1.0 = no smoothing
  - Only used when `filter_method=exponential`
  - Example: `filter_alpha=0.3`

- **`filter_q`** (optional, default: 0.001)
  - Process noise covariance for Kalman filter
  - Range: > 0.0
  - Only used when `filter_method=kalman`
  - Example: `filter_q=0.01`

- **`filter_r`** (optional, default: 1.0)
  - Measurement noise covariance for Kalman filter
  - Range: > 0.0
  - Only used when `filter_method=kalman`
  - Example: `filter_r=2.0`

### Threshold Parameters

- **`threshold`** (optional, default: "0.0")
  - Threshold for change detection
  - Single value (broadcast to all 10 loadcells): `threshold=5.0`
  - Per-loadcell (comma-separated): `threshold=5.0,10.0,5.0,5.0,5.0,5.0,5.0,5.0,5.0,5.0`
  - Example: `threshold=10.0`

- **`threshold_scope`** (optional, default: `filtered`)
  - Apply threshold to raw or filtered values
  - Valid values: `raw`, `filtered`
  - Example: `threshold_scope=raw`

## Usage Examples

### Example 1: High-Frequency Loadcell Monitoring

Monitor loadcells at 10 Hz (0.1s interval) with no filtering:

```bash
curl "http://localhost:8000/sse?streams=loadcells&loadcell_interval=0.1&filter_method=none"
```

### Example 2: Smooth Loadcell Monitoring with Exponential Filter

Apply exponential smoothing for noise reduction:

```bash
curl "http://localhost:8000/sse?streams=loadcells&loadcell_interval=0.5&filter_method=exponential&filter_alpha=0.2"
```

### Example 3: Anti-Theft Monitoring with Kalman Filter

Use Kalman filter with tight threshold for theft detection:

```bash
curl "http://localhost:8000/sse?streams=loadcells&loadcell_interval=0.2&filter_method=kalman&filter_q=0.001&filter_r=1.0&threshold=5.0&threshold_scope=filtered"
```

### Example 4: Per-Loadcell Threshold Configuration

Set different thresholds for each loadcell (e.g., heavier items need higher thresholds):

```bash
curl "http://localhost:8000/sse?streams=loadcells&threshold=5.0,10.0,5.0,8.0,5.0,5.0,12.0,5.0,5.0,5.0"
```

### Example 5: Raw Value Threshold (No Filtering)

Monitor raw values directly with threshold on raw readings:

```bash
curl "http://localhost:8000/sse?streams=loadcells&filter_method=none&threshold=10.0&threshold_scope=raw"
```

### Example 6: Combined Loadcell and Door Monitoring

Monitor both streams with different intervals:

```bash
curl "http://localhost:8000/sse?streams=loadcells,doors&loadcell_interval=0.2&door_interval=1.0&filter_method=exponential&filter_alpha=0.3&threshold=8.0"
```

### Example 7: Door-Only Monitoring

Monitor only door status (useful for access control):

```bash
curl "http://localhost:8000/sse?streams=doors&door_interval=0.5"
```

## JavaScript Client Example

```javascript
const eventSource = new EventSource(
  'http://localhost:8000/sse?streams=loadcells,doors&loadcell_interval=0.5&door_interval=1.0&filter_method=exponential&filter_alpha=0.3&threshold=5.0'
);

// Handle loadcell updates
eventSource.addEventListener('loadcell.update', (event) => {
  const data = JSON.parse(event.data);
  console.log('Loadcell update:', data);
  updateLoadcellDisplay(data.filtered_values);
});

// Handle threshold changes (anti-theft events)
eventSource.addEventListener('loadcell.change', (event) => {
  const data = JSON.parse(event.data);
  console.warn('Loadcell change detected:', data);
  triggerAlert(data.changed_indices);
});

// Handle uncertainty events (critical anti-theft)
eventSource.addEventListener('loadcell.uncertainty', (event) => {
  const data = JSON.parse(event.data);
  console.error('Loadcell uncertainty:', data);
  if (data.reason === 'io_board_failure') {
    displayConnectionError();
  } else {
    triggerAntiTheftAlert(data.affected_indices);
  }
});

// Handle door updates
eventSource.addEventListener('door.update', (event) => {
  const data = JSON.parse(event.data);
  console.log('Door status:', data);
  updateDoorDisplay(data.door, data.deadbolt);
});

// Handle errors
eventSource.addEventListener('error', (event) => {
  const data = JSON.parse(event.data);
  console.error('Stream error:', data);
});

// Connection management
eventSource.onerror = (error) => {
  console.error('SSE connection error:', error);
  // EventSource will automatically reconnect
};
```

## Python Client Example

```python
import requests
import json

url = "http://localhost:8000/sse"
params = {
    "streams": "loadcells,doors",
    "loadcell_interval": 0.5,
    "door_interval": 1.0,
    "filter_method": "exponential",
    "filter_alpha": 0.3,
    "threshold": "5.0",
    "threshold_scope": "filtered"
}

with requests.get(url, params=params, stream=True) as response:
    for line in response.iter_lines():
        if not line:
            continue
        
        line_str = line.decode('utf-8')
        
        if line_str.startswith('event:'):
            event_type = line_str.split(':', 1)[1].strip()
        elif line_str.startswith('data:'):
            data_str = line_str.split(':', 1)[1].strip()
            data = json.loads(data_str)
            
            if event_type == 'loadcell.update':
                print(f"Loadcell update: {data['filtered_values']}")
            elif event_type == 'loadcell.change':
                print(f"⚠️  Change detected on loadcells: {data['changed_indices']}")
            elif event_type == 'loadcell.uncertainty':
                print(f"🚨 Uncertainty on loadcells: {data['affected_indices']} - {data['reason']}")
            elif event_type == 'door.update':
                print(f"Door: {data['door']}, Deadbolt: {data['deadbolt']}")
            elif event_type == 'error':
                print(f"❌ Error in {data.get('stream', 'unknown')}: {data.get('message', 'Unknown error')}")
```

## Filter Selection Guide

### No Filter (`filter_method=none`)
- **Use when:** You need raw, unprocessed data
- **Pros:** Zero latency, no smoothing artifacts
- **Cons:** Noisy data, prone to false positives
- **Best for:** High-quality sensors, debugging

### Exponential Smoothing (`filter_method=exponential`)
- **Use when:** You want simple, effective noise reduction
- **Pros:** Easy to configure (single alpha parameter), low computational cost
- **Cons:** Introduces lag proportional to smoothing strength
- **Best for:** General-purpose anti-theft monitoring
- **Recommended alpha:** 0.2-0.3 for loadcells

### Kalman Filter (`filter_method=kalman`)
- **Use when:** You need optimal noise reduction with minimal lag
- **Pros:** Best noise reduction, adapts to measurement quality
- **Cons:** Requires tuning Q and R parameters
- **Best for:** Critical anti-theft applications, high-noise environments
- **Recommended values:** Q=0.001, R=1.0 for loadcells

## Threshold Scope Selection

### Raw Scope (`threshold_scope=raw`)
- Threshold applied to **raw unfiltered values**
- **Use when:** You want immediate response to changes
- **Pros:** No lag, instant detection
- **Cons:** Prone to false positives from sensor noise

### Filtered Scope (`threshold_scope=filtered`)
- Threshold applied to **filtered values**
- **Use when:** You want stable, noise-resistant detection
- **Pros:** Reduces false positives, stable operation
- **Cons:** Slight delay due to filtering

**Recommendation:** Use `filtered` scope with exponential or Kalman filter for production anti-theft systems.

## Error Handling

The SSE stream is designed to be resilient:

1. **I/O Board Failures:** Stream continues, emits `loadcell.uncertainty` events with `reason="io_board_failure"`
2. **Individual Loadcell Errors:** Emits `loadcell.uncertainty` with affected indices
3. **Parse Failures:** Treated as uncertainty events
4. **Filter State:** Automatically reset on I/O board reconnection to avoid stale state

**Client reconnection:** EventSource API automatically reconnects on connection loss.

## OpenAPI Documentation

Full API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Deprecated Endpoint

The legacy `/stream/loadcells` endpoint is deprecated in favor of the unified `/sse` endpoint.

**Migration:**
```bash
# Old (deprecated)
curl "http://localhost:8000/stream/loadcells"

# New (recommended)
curl "http://localhost:8000/sse?streams=loadcells"
```

The old endpoint will continue to work but will log deprecation warnings.
