# SSE Endpoint Documentation Index

Complete documentation for the unified Server-Sent Events streaming endpoint at `/sse`

## Quick Navigation

### For First-Time Users
Start here: **[SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md)**
- Quick examples for common use cases
- Minimal parameter reference
- Event type overview
- Basic client code snippets

### For API Integration
Read: **[SSE_API_REFERENCE.md](SSE_API_REFERENCE.md)**
- Complete parameter specifications
- All query parameters explained
- HTTP headers and status codes
- Rate limiting information
- Full request/response specifications

### For Event Details
Read: **[SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md)**
- Detailed event type specifications
- JSON schema for each event
- Real examples of each event
- Client-side handling patterns
- Timestamp formats
- Performance considerations

### For Usage Examples
Read: **[SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md)**
- Real-world usage examples
- Common scenarios explained
- Multi-language client examples
- Filter selection guide
- Threshold configuration guide
- Error handling strategies

### For Code Documentation
Check: [src/io_board/api.py](src/io_board/api.py)
- Comprehensive endpoint docstring
- Inline event format documentation
- Implementation details

---

## Document Descriptions

### 1. SSE_QUICK_REFERENCE.md
**Best for:** Quick lookup, common scenarios, getting started

**Contains:**
- Endpoint URL and HTTP method
- Quick example queries
- Parameter quick table
- Event types quick reference
- JSON structure samples for each event
- JavaScript and Python code snippets
- Common use cases (anti-theft, inventory, access control, combined)
- Filter selection matrix
- Deprecation notice

**Read time:** 5 minutes

---

### 2. SSE_API_REFERENCE.md
**Best for:** API implementation, parameter validation, integration

**Contains:**
- Complete endpoint specification
- Required vs optional parameters
- Parameter ranges and validation rules
- Default values for all parameters
- HTTP headers and response codes
- Detailed semantics for each parameter
- Error response formats
- Behavior specifications (timing, error handling, connections)
- Rate limiting
- OpenAPI documentation location
- Complete examples

**Read time:** 15 minutes

---

### 3. SSE_STREAMING_RESPONSE_FORMAT.md
**Best for:** Understanding event formats, client implementation

**Contains:**
- SSE protocol format explanation
- All 5 event types in detail:
  - `loadcell.update` - periodic readings
  - `loadcell.change` - threshold breaches
  - `loadcell.uncertainty` - errors (anti-theft)
  - `door.update` - door status
  - `error` - stream-level errors
- JSON schema for each event
- Real example payloads
- Field-by-field documentation
- Preconditions for each event
- Client-side handling patterns
- JavaScript and Python examples
- Timestamp format specification
- Error handling strategies
- Performance metrics
- Testing methods

**Read time:** 20 minutes

---

### 4. SSE_USAGE_EXAMPLES.md
**Best for:** Learning by example, best practices

**Contains:**
- High-frequency loadcell monitoring
- Smooth monitoring with exponential filter
- Anti-theft with Kalman filter
- Per-loadcell threshold configuration
- Raw value threshold monitoring
- Combined loadcell and door monitoring
- Door-only monitoring
- JavaScript EventSource client example
- Python requests client example
- Filter selection guide with pros/cons
- Threshold scope explanation
- OpenAPI documentation location
- Deprecated endpoint migration guide

**Read time:** 12 minutes

---

## Quick Links

### By Use Case

**🚨 Anti-Theft Monitoring**
1. Read: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#anti-theft-monitoring-high-sensitivity)
2. Read: [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#3-loadcell_uncertainty-event)
3. Implement: See JavaScript/Python examples

**📊 Warehouse Inventory**
1. Read: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#warehouse-inventory-tracking-low-overhead)
2. Check parameters: [SSE_API_REFERENCE.md](SSE_API_REFERENCE.md#filter_alpha-float-optional)

**🚪 Door Access Control**
1. Read: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#door-access-control)
2. Focus on: [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#4-door_update-event)

**⚙️ Combined Monitoring**
1. Read: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#combined-monitoring)
2. See: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#example-6-combined-loadcell-and-door-monitoring)

---

### By Topic

**Parameters**
- Quick summary: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#quick-examples)
- Complete specs: [SSE_API_REFERENCE.md](SSE_API_REFERENCE.md#request)
- Usage guide: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#query-parameters)

**Events**
- Overview: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#event-types-emitted)
- Detailed: [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#event-types-and-formats)
- Real examples: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#event-types)

**Filtering**
- Quick guide: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#filter-selection)
- Detailed: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#filter-selection-guide)
- API spec: [SSE_API_REFERENCE.md](SSE_API_REFERENCE.md#filter-parameters)

**Thresholds**
- Examples: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#optional-parameters)
- Guide: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#example-4-per-loadcell-threshold-configuration)
- Spec: [SSE_API_REFERENCE.md](SSE_API_REFERENCE.md#threshold-parameters)

**Client Implementation**
- JavaScript: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#javascript) and [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#javascript-eventsource-api)
- Python: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#python) and [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#python-requests-library)

**Error Handling**
- Quick overview: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#important-notes)
- Detailed: [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#error-handling-strategy)
- API spec: [SSE_API_REFERENCE.md](SSE_API_REFERENCE.md#error-responses)

---

## Document Relationships

```
SSE_QUICK_REFERENCE
├─ Quick start for everyone
├─ Links to specific topics
└─ Typical reading order for new users

SSE_API_REFERENCE
├─ Complete parameter documentation
├─ HTTP status codes
└─ Specification-level detail

SSE_STREAMING_RESPONSE_FORMAT
├─ Event type details
├─ JSON schemas
├─ Client code examples
└─ Performance considerations

SSE_USAGE_EXAMPLES
├─ Practical examples
├─ Best practices
├─ Filter selection guide
└─ Real-world scenarios
```

---

## Key Concepts

### Anti-Theft Events
- **`loadcell.uncertainty` events** - Treat as security events
- **Any uncertainty = potential theft/tampering** - Immediate action required
- **Filter state resets on I/O failure** - Prevents stale readings

See: [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#3-loadcell_uncertainty-event)

### Filtering Options
- **`none`** - Raw data, immediate response
- **`exponential`** - Configurable smoothing with alpha parameter
- **`kalman`** - Optimal filtering with Q/R parameters

See: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#filter-selection-guide)

### Threshold Modes
- **`raw` scope** - Threshold on unfiltered values (immediate but noisy)
- **`filtered` scope** - Threshold on filtered values (stable, recommended)

See: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#threshold-scope-selection)

### Stream Independence
- **Loadcell and door streams have separate intervals**
- **Allows optimized polling for each stream type**
- **Independent error handling per stream**

See: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#combined-with-filtering)

---

## Testing Resources

### Using curl
```bash
curl -N "http://localhost:8000/sse?streams=loadcells&threshold=10.0"
```

### Browser Testing
```javascript
const es = new EventSource('http://localhost:8000/sse?streams=loadcells');
es.onmessage = (e) => console.log(e.data);
```

### Test Script
See [test_sse_feature.py](test_sse_feature.py) for unit tests of filter implementations

See: [SSE_STREAMING_RESPONSE_FORMAT.md](SSE_STREAMING_RESPONSE_FORMAT.md#testing-event-streams)

---

## Common Troubleshooting

**"Invalid stream names" error**
→ Check [SSE_API_REFERENCE.md](SSE_API_REFERENCE.md#streams-string-required) for valid values

**"Wrong number of threshold values"**
→ Read [SSE_API_REFERENCE.md](SSE_API_REFERENCE.md#threshold-string-optional) - must be 1 or 10 values

**Too much noise in readings**
→ Use filtering: [SSE_USAGE_EXAMPLES.md](SSE_USAGE_EXAMPLES.md#filter-selection-guide)

**False positive change events**
→ Adjust threshold or use smoothing: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#common-use-cases)

**Want to migrate from /stream/loadcells**
→ See deprecation notice: [SSE_QUICK_REFERENCE.md](SSE_QUICK_REFERENCE.md#deprecation-notice)

---

## Version History

- **v2.0.0** (Current) - Unified `/sse` endpoint with configurable filtering and thresholds
- **v1.0.0** (Deprecated) - Legacy `/stream/loadcells` endpoint

---

## More Information

**Interactive API Documentation:**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

**Source Code:**
- Endpoint implementation: [src/io_board/api.py](src/io_board/api.py)
- Filter implementations: [src/io_board/filters.py](src/io_board/filters.py)
- Event detection: [src/io_board/events.py](src/io_board/events.py)
- Data models: [src/io_board/io_types.py](src/io_board/io_types.py)

**Testing:**
- Unit tests: [test_sse_feature.py](test_sse_feature.py)
