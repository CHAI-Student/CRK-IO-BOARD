# IO Board Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         IO Board Control Service                     │
│                            Version 2.0.0                             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      External Dependencies                           │
├─────────────────────────────────────────────────────────────────────┤
│  • FastAPI (Web Framework)                                          │
│  • Uvicorn (ASGI Server)                                            │
│  • Pydantic (Data Validation)                                       │
│  • PySerial + PySerial-Asyncio (Serial Communication)               │
│  • Construct (Binary Protocol)                                      │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      Application Entry Point                         │
├─────────────────────────────────────────────────────────────────────┤
│  main.py                                                            │
│  • Load configuration from environment                               │
│  • Setup structured logging                                         │
│  • Configure serial communication                                   │
│  • Start FastAPI server                                             │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────┬────────────────────────────────────────┐
│   Configuration Layer      │      Logging Layer                     │
├────────────────────────────┼────────────────────────────────────────┤
│  config.py                 │   logging_config.py                    │
│  • SerialConfig            │   • Correlation ID tracking            │
│  • APIConfig               │   • Structured logging                 │
│  • Environment variables   │   • Performance metrics                │
│  • Validation              │   • Binary payload logging             │
└────────────────────────────┴────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         API Layer (REST)                             │
├─────────────────────────────────────────────────────────────────────┤
│  api.py - FastAPI Application                                       │
│                                                                      │
│  Middleware:                                                         │
│  • Request/Response Logging                                         │
│  • Correlation ID Management                                        │
│                                                                      │
│  Exception Handlers:                                                │
│  • IOBoardError → Standard Error Response                           │
│  • ValidationError → 422 Response                                   │
│  • Generic Exception → 500 Response                                 │
│                                                                      │
│  Endpoints:                                                          │
│  ┌──────────────────┬──────────────────┬─────────────────────────┐ │
│  │ Device Mgmt      │ Door Control     │ Sensors & Info          │ │
│  ├──────────────────┼──────────────────┼─────────────────────────┤ │
│  │ POST /init       │ POST /deadbolt   │ GET /loadcells          │ │
│  │ POST /calibrate  │                  │ GET /status             │ │
│  │ POST /mfg_number │                  │ GET /product_info       │ │
│  │ DELETE /errors   │                  │ GET /errors             │ │
│  │ POST /reboot     │                  │ GET /stream/loadcells   │ │
│  └──────────────────┴──────────────────┴─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      Business Logic Layer                            │
├─────────────────────────────────────────────────────────────────────┤
│  commands.py - High-Level Device Commands                           │
│                                                                      │
│  Device Control:              Data Retrieval:                       │
│  • initialize()               • get_product_info()                  │
│  • set_door_state()           • get_loadcells()                     │
│  • calibrate()                • get_io_status()                     │
│  • set_manufacturing_number() • get_errors()                        │
│  • clear_errors()                                                   │
│  • reboot()                                                         │
│                                                                      │
│  Features:                                                           │
│  • Comprehensive docstrings                                         │
│  • Type hints                                                       │
│  • Error handling and logging                                       │
│  • Performance tracking                                             │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   Serial Communication Layer                         │
├─────────────────────────────────────────────────────────────────────┤
│  serial_io.py - Async Serial Communication                          │
│                                                                      │
│  Key Functions:                                                      │
│  • configure_serial() - Set configuration                           │
│  • fetch() - Send/receive with retry logic                          │
│                                                                      │
│  Features:                                                           │
│  • Mutex-based exclusive access                                     │
│  • Exponential backoff retry (configurable)                         │
│  • Timeout handling (header/body/checksum)                          │
│  • Binary payload logging (TX/RX)                                   │
│  • Categorized error handling                                       │
│  • Automatic connection management                                  │
│                                                                      │
│  Retry Strategy:                                                     │
│  Attempt 1: Wait 100ms                                              │
│  Attempt 2: Wait 200ms (exponential backoff)                        │
│  Attempt 3: Wait 400ms                                              │
│  Fail: Raise SerialCommunicationError with context                  │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                       Protocol Layer                                 │
├─────────────────────────────────────────────────────────────────────┤
│  protocol.py - Binary Protocol Implementation                       │
│                                                                      │
│  Frame Structure:                                                    │
│  [STX 0x02][CMD 2B][SUBCMD 2B][DATA VAR][ETX 0x03][CHECKSUM 1B]    │
│                                                                      │
│  Key Functions:                                                      │
│  • build_request() - Encode request messages                        │
│  • parse_response() - Decode response messages                      │
│  • calculate_checksum() - XOR checksum                              │
│                                                                      │
│  Commands:                                                           │
│  ┌────────────────────┬──────────────────────────────────────────┐ │
│  │ Management (MC)    │ Request (RQ)                            │ │
│  ├────────────────────┼──────────────────────────────────────────┤ │
│  │ PD - Initialize    │ MI - Manufacturing Info                 │ │
│  │ DC - Door Control  │ IW - Loadcell Weights (10 readings)    │ │
│  │ LZ - Calibrate     │ ID - IO Status (door + deadbolt)       │ │
│  │ WP - Write Product │ ER - Error List (4 error codes)        │ │
│  │ EZ - Clear Errors  │                                         │ │
│  │ RT - Reboot        │                                         │ │
│  └────────────────────┴──────────────────────────────────────────┘ │
│                                                                      │
│  Error Handling:                                                     │
│  • Checksum validation                                              │
│  • Frame marker validation (STX/ETX)                                │
│  • Specific error codes for each failure type                       │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Hardware Interface                                │
├─────────────────────────────────────────────────────────────────────┤
│  Serial Port (RS-232/USB)                                           │
│  • COM3 (Windows) or /dev/ttyUSB0 (Linux) - configurable           │
│  • 38400 baud - configurable                                        │
│  • 8N1 (8 data bits, no parity, 1 stop bit)                        │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      IO Board Device                                 │
├─────────────────────────────────────────────────────────────────────┤
│  • 10 Loadcells (weight sensors)                                    │
│  • Door sensor                                                       │
│  • Deadbolt sensor                                                   │
│  • Door lock control                                                 │
│  • Error logging                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    Cross-Cutting Concerns                            │
├─────────────────────────────────────────────────────────────────────┤
│  types.py - Type Definitions                                        │
│  • Enums (CommandType, DoorState, ErrorCode)                        │
│  • TypedDicts (Protocol structures)                                 │
│  • Pydantic Models (API request/response)                           │
│                                                                      │
│  exceptions.py - Exception Hierarchy                                │
│  • IOBoardError (base)                                              │
│    ├─ ConfigurationError (E1xxx)                                    │
│    ├─ SerialCommunicationError (E2xxx)                              │
│    ├─ ProtocolError (E3xxx)                                         │
│    ├─ ValidationError (E4xxx)                                       │
│    └─ DeviceError (E5xxx)                                           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         Data Flow Example                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  HTTP Request: POST /deadbolt {"state": "OPEN"}                     │
│       ↓                                                              │
│  [API Layer] Validate request, log with correlation ID              │
│       ↓                                                              │
│  [Commands Layer] set_door_state(DoorState.OPEN)                    │
│       ↓                                                              │
│  [Protocol Layer] build_request("MC", "DC", {"DOOR": ord("O")})     │
│       ↓                                                              │
│  [Serial Layer] fetch(message) with retry logic                     │
│       ↓                                                              │
│  [Hardware] Send: 02 4D 43 44 43 4F 03 0A (hex)                     │
│       ↓                                                              │
│  [Hardware] Recv: 02 4D 43 44 43 4F 03 0A (hex)                     │
│       ↓                                                              │
│  [Serial Layer] Return binary response                              │
│       ↓                                                              │
│  [Protocol Layer] parse_response(message)                           │
│       ↓                                                              │
│  [Commands Layer] Return DoorState.OPEN                             │
│       ↓                                                              │
│  [API Layer] Return {"state": "OPEN"}, log completion time          │
│       ↓                                                              │
│  HTTP Response: 200 OK {"state": "OPEN"}                            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      Error Flow Example                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Serial Timeout Occurs                                               │
│       ↓                                                              │
│  [Serial Layer] Retry 1: Wait 100ms → Fail                          │
│       ↓                                                              │
│  [Serial Layer] Retry 2: Wait 200ms → Fail                          │
│       ↓                                                              │
│  [Serial Layer] Retry 3: Wait 400ms → Fail                          │
│       ↓                                                              │
│  [Serial Layer] Raise SerialCommunicationError(                     │
│                     error_code=ErrorCode.SERIAL_TIMEOUT,            │
│                     details={"port": "COM3", "attempts": 3}         │
│                 )                                                    │
│       ↓                                                              │
│  [Commands Layer] Log error, re-raise                               │
│       ↓                                                              │
│  [API Layer] Exception handler catches IOBoardError                 │
│       ↓                                                              │
│  [API Layer] Return JSONResponse(                                   │
│                  status_code=500,                                   │
│                  content={                                          │
│                      "error_code": "E2005",                         │
│                      "message": "Serial read timeout...",           │
│                      "details": {"port": "COM3", ...}               │
│                  }                                                  │
│              )                                                       │
│       ↓                                                              │
│  HTTP Response: 500 Internal Server Error                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

Legend:
━━━━━  Data flow
──────  Component boundary
│      Vertical connection
```

## Key Architecture Principles

1. **Layered Architecture**: Clear separation of concerns
2. **Dependency Inversion**: High-level modules don't depend on low-level details
3. **Single Responsibility**: Each module has one clear purpose
4. **Open/Closed**: Open for extension, closed for modification
5. **Error Handling**: Comprehensive at every layer
6. **Type Safety**: Strong typing throughout
7. **Observability**: Logging and metrics at every layer
8. **Configuration**: Externalized and validated

## Component Responsibilities

- **main.py**: Bootstrap and configuration
- **config.py**: Configuration management
- **logging_config.py**: Observability infrastructure
- **api.py**: HTTP interface
- **commands.py**: Business logic
- **serial_io.py**: Hardware communication
- **protocol.py**: Binary protocol handling
- **types.py**: Type system
- **exceptions.py**: Error handling

## Data Flow Summary

```
HTTP Request
    ↓
API Validation
    ↓
Business Logic
    ↓
Protocol Encoding
    ↓
Serial Communication
    ↓
Hardware
    ↓
Serial Response
    ↓
Protocol Decoding
    ↓
Business Logic
    ↓
API Response
    ↓
HTTP Response
```

## Error Propagation

```
Hardware Error
    ↓
Serial Exception
    ↓
Protocol Exception (if applicable)
    ↓
Command Exception
    ↓
API Exception Handler
    ↓
Standard Error Response
```
