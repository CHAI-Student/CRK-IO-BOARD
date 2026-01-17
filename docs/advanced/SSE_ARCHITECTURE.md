# SSE Endpoint Architecture and Flow Diagrams

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     HTTP Client (Browser/App)                   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 │ GET /sse?streams=loadcells,doors
                                 │     &filter_method=exponential
                                 │     &threshold=10.0
                                 │
                    ┌────────────▼────────────┐
                    │   FastAPI App           │
                    │   (/sse endpoint)       │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
   ┌─────────────┐         ┌──────────────┐         ┌──────────────┐
   │  Query Param │         │   Validators │         │  Event Queue │
   │  Parser     │         │              │         │  (asyncio)   │
   └──────┬──────┘         └──────────────┘         └──────────────┘
          │
          ▼
   ┌─────────────────────────────────────────┐
   │  async def unified_event_generator()    │
   │  ┌─────────────────────────────────────┐│
   │  │ poll_loadcells()  ← Task 1          ││
   │  │ ├─ commands.get_loadcells()         ││
   │  │ ├─ LoadcellChangeDetector.process() ││
   │  │ ├─ Emit loadcell.update             ││
   │  │ ├─ Emit loadcell.change (if delta)  ││
   │  │ └─ Emit loadcell.uncertainty (if error)││
   │  └─────────────────────────────────────┘│
   │  ┌─────────────────────────────────────┐│
   │  │ poll_doors()  ← Task 2              ││
   │  │ ├─ commands.get_io_status()         ││
   │  │ ├─ Emit door.update                 ││
   │  │ └─ Emit error (if communication fail)││
   │  └─────────────────────────────────────┘│
   │  Event Queue Consumer                    │
   │  └─ Yield SSE formatted: event: X\ndata:Y\n\n
   └─────────────────────────────────────────┘
        │
        │ StreamingResponse
        │ Content-Type: text/event-stream
        │ Cache-Control: no-cache
        │ Connection: keep-alive
        │
        ▼
   ┌──────────────────────────────┐
   │  SSE Stream to Client        │
   │  (continuous data flow)      │
   └──────────────────────────────┘
```

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    LOADCELL STREAM FLOW                          │
└──────────────────────────────────────────────────────────────────┘

I/O Board Serial Connection
        │
        ▼
  get_loadcells() [10 raw values]
        │
        ├─ "+12345", "+00123", "-00456", ... (10 items)
        │
        ▼
  LoadcellChangeDetector.process()
        │
        ├─ Apply Filter (NoFilter/Exponential/Kalman)
        │  ├─ Input:  raw_value (string)
        │  └─ Output: filtered_value (float) + error handling
        │
        ├─ Track Previous Values
        │  └─ _previous_raw, _previous_filtered (per loadcell)
        │
        ├─ Detect Changes (threshold scope: raw/filtered)
        │  ├─ new - old > threshold?
        │  ├─ YES → Add to changed_indices
        │  └─ NO  → Continue
        │
        ├─ Detect Uncertainties
        │  ├─ Error codes? (EEEEEE, VVVVVV)
        │  ├─ Parse failures?
        │  └─ YES → Mark uncertain
        │
        └─ Return: (filtered_strings, filtered_numerics, changed_indices, details)
           │
           ├─ If changed:   Emit loadcell.change
           ├─ If uncertain: Emit loadcell.uncertainty (ANTI-THEFT!)
           └─ Always:       Emit loadcell.update

┌──────────────────────────────────────────────────────────────────┐
│                    DOOR STREAM FLOW                              │
└──────────────────────────────────────────────────────────────────┘

I/O Board Serial Connection
        │
        ▼
  get_io_status() [door + deadbolt]
        │
        ├─ "CLOSED" / "OPENED" / "ERROR_"
        │
        ▼
  Emit door.update
        │
        └─ {timestamp, door, deadbolt}
```

---

## State Machine: Filter Lifecycle

```
┌────────────────────────────────────────────────────────────────┐
│                   FILTER STATE MACHINE                         │
└────────────────────────────────────────────────────────────────┘

                      ┌─────────────┐
                      │ Initialized │
                      │   = False   │
                      └──────┬──────┘
                             │
                             │ filter(first_valid_reading)
                             │
                      ┌──────▼────────┐
                      │ Initialize    │
                      │ _previous =   │
                      │ first_reading │
                      └──────┬────────┘
                             │
                      ┌──────▼────────┐
                      │ Initialized   │
                      │   = True      │
                      └──────┬────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
                    │ (normal reads)  │
                    │                 │
                    ▼                 ▼
          ┌─────────────────┐  ┌──────────────┐
          │ Valid Value     │  │ Error Value  │
          │ Apply Filter    │  │ (skip filter)│
          │ Update _prev    │  │ (no change)  │
          └────────┬────────┘  └──────┬───────┘
                   │                  │
                   └──────────┬───────┘
                              │
                    ┌─────────▼─────────┐
                    │  I/O Board Fails  │
                    │    reset()        │
                    │ ↓                 │
                    │ Initialized=False │
                    │ _previous = None  │
                    └─────────┬─────────┘
                              │
                    (restart cycle on reconnect)
```

---

## Event Emission Decision Tree

```
┌───────────────────────────────────────────────────────────────────┐
│              WHEN TO EMIT EACH EVENT TYPE                         │
└───────────────────────────────────────────────────────────────────┘

                    New Loadcell Reading
                           │
                           ▼
        ┌──────────────────────────────────┐
        │  ALWAYS Emit loadcell.update     │
        │  (raw + filtered values)         │
        └──────────────────────────────────┘
                           │
              ┌────────────┴───────────────┐
              │                            │
              ▼                            ▼
    ┌──────────────────────┐    ┌──────────────────────┐
    │ Error Detected?      │    │ Value Changed?       │
    │ (EEEEEE, VVVVVV)    │    │ (|new - old|>thresh?)│
    │ or I/O Fail?        │    │                      │
    └──────────┬───────────┘    └──────────┬───────────┘
               │                           │
              YES                         YES
               │                           │
               ▼                           ▼
    ┌─────────────────────┐    ┌──────────────────────┐
    │ Emit               │    │ Emit                 │
    │ loadcell.          │    │ loadcell.change      │
    │ uncertainty        │    │ (with indices,       │
    │ (ANTI-THEFT!)      │    │  old/new, deltas)    │
    │ ✓ Filter resets    │    │ ✓ No special action  │
    └──────────┬───────────┘    └──────────┬───────────┘
               │                           │
               └────────────┬──────────────┘
                            │
                     (stream continues)
```

---

## Parameter Flow Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                    PARAMETER PROCESSING                           │
└───────────────────────────────────────────────────────────────────┘

Query String
    │
    ├─ streams=loadcells,doors
    │  ├─ Parse: ["loadcells", "doors"]
    │  ├─ Validate: OK (both valid)
    │  └─ Pass to: enabled_streams list
    │
    ├─ loadcell_interval=0.5
    │  ├─ Validate: 0.1 ≤ 0.5 ≤ 10.0 → OK
    │  └─ Pass to: poll_loadcells() task
    │
    ├─ door_interval=1.0
    │  ├─ Validate: 0.1 ≤ 1.0 ≤ 10.0 → OK
    │  └─ Pass to: poll_doors() task
    │
    ├─ filter_method=exponential
    │  ├─ Validate: valid enum → OK
    │  └─ Pass to: create_filter(FilterMethod.EXPONENTIAL)
    │
    ├─ filter_alpha=0.3
    │  ├─ Validate: 0.0 ≤ 0.3 ≤ 1.0 → OK
    │  ├─ Clamp: No change needed
    │  └─ Pass to: ExponentialSmoothingFilter(alpha=0.3)
    │
    ├─ threshold=5.0,10.0,5.0,...(10 values)
    │  ├─ Parse: ["5.0", "10.0", "5.0", ...]
    │  ├─ Validate: 10 values → OK
    │  ├─ Convert: [5.0, 10.0, 5.0, ...]
    │  └─ Pass to: LoadcellChangeDetector(thresholds=[...])
    │
    └─ threshold_scope=filtered
       ├─ Validate: valid enum → OK
       └─ Pass to: LoadcellChangeDetector(threshold_scope=ThresholdScope.FILTERED)
```

---

## Filter Comparison Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│               FILTER OUTPUT COMPARISON                            │
└───────────────────────────────────────────────────────────────────┘

Input: Raw readings with noise
  100, 105, 98, 102, 99, 101, 103, 97, 104, 100

┌──────────────────────────────────────┐
│ NoFilter (filter_method=none)        │
│ Output: 100, 105, 98, 102, 99, ...   │
│ ✓ Zero latency                       │
│ ✗ Noisy, prone to false positives    │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│ ExponentialSmoothing (alpha=0.3)     │
│ Output: 100, 101.5, 99.8, 101, ...   │
│ ✓ Simple, configurable               │
│ ✓ Smooth, good for general use       │
│ ~ Slight lag from smoothing          │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│ Kalman Filter (Q=0.001, R=1.0)       │
│ Output: 100, 101.2, 99.9, 101.1, ... │
│ ✓ Optimal smoothing                  │
│ ✓ Adaptive to measurement quality    │
│ ~ More complex to tune               │
└──────────────────────────────────────┘

Visual comparison over time:
┌─────────────────────────────────────────────┐
│       105 ┤      ╱╲                         │
│       104 ┤     ╱  ╲                        │
│       103 ┤ No Filter: ╱╲╱╲                 │
│       102 ┤╱╲╱╲╱╲╱╲╱╱╲╱╲                  │
│       101 ┤     ┌────┐ Exponential: smooth│
│       100 ┤────┘    └────                  │
│        99 ┤ Kalman: ─────── (smoothest)   │
│        98 ┤                                │
│       └─────────────────────────────────────┘
│          0   5   10  15  20  25  30  time
```

---

## Threshold Scope Comparison

```
┌───────────────────────────────────────────────────────────────────┐
│            THRESHOLD SCOPE: RAW vs FILTERED                       │
└───────────────────────────────────────────────────────────────────┘

Scenario: Weight decreases from 1000g to 990g (10g change, threshold=5g)

RAW SCOPE (threshold_scope=raw):
  ├─ Previous raw: 1000
  ├─ Current raw: 990
  ├─ Delta: |990 - 1000| = 10
  ├─ Compare: 10 > 5? → YES ✓
  └─ Result: Emit loadcell.change (IMMEDIATE)

FILTERED SCOPE (threshold_scope=filtered):
  ├─ Previous filtered: 1000
  ├─ Current raw: 990
  ├─ Apply filter (EMA, alpha=0.3):
  │  filtered = 0.3*990 + 0.7*1000 = 297 + 700 = 997
  ├─ Delta: |997 - 1000| = 3
  ├─ Compare: 3 > 5? → NO ✗
  └─ Result: No event emitted yet (need bigger change)

   If next reading is 980g:
  ├─ Current raw: 980
  ├─ Apply filter: 0.3*980 + 0.7*997 = 294 + 697.9 = 991.9
  ├─ Delta: |991.9 - 997| = 5.1
  ├─ Compare: 5.1 > 5? → YES ✓
  └─ Result: Emit loadcell.change (AFTER SMOOTHING)

Summary:
  Raw scope:      Fast but noisy
  Filtered scope: Slower but stable (RECOMMENDED)
```

---

## Connection Lifecycle Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│              SSE CONNECTION LIFECYCLE                             │
└───────────────────────────────────────────────────────────────────┘

Client Connection Established
        │
        ▼
GET /sse?streams=... HTTP/1.1
        │
        ├─ Parse query params
        ├─ Validate parameters
        └─ If invalid: Return 422 ✗
                │
                ▼
           Connection CLOSED
           (client reconnects)
        
        If valid: ✓
        │
        ▼
Create polling tasks
  ├─ poll_loadcells() (if enabled)
  └─ poll_doors() (if enabled)
        │
        ▼
StreamingResponse (200 OK)
  ├─ Content-Type: text/event-stream
  ├─ Cache-Control: no-cache
  └─ Connection: keep-alive
        │
        ▼
Event Stream Flow
  ├─ Emit events continuously
  ├─ Handle I/O errors gracefully
  ├─ Reset filters on reconnection
  └─ Monitor client disconnect
        │
        ├─ Client Disconnected? → YES
        │  ├─ Cancel tasks
        │  ├─ Clean up resources
        │  └─ End stream ✓
        │
        ├─ Server Shutdown? → YES
        │  ├─ Graceful task termination
        │  └─ All streams close ✓
        │
        └─ Normal operation continues...
```

---

## Error Handling Flow

```
┌───────────────────────────────────────────────────────────────────┐
│              ERROR HANDLING & RECOVERY                            │
└───────────────────────────────────────────────────────────────────┘

                    Polling Task Running
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
    Success          IOBoardError         Unexpected Error
        │             (expected)          (catch-all)
        │                   │                   │
        ├─ Read from I/O   ├─ Log warning     ├─ Log error
        ├─ Process data    ├─ Emit error      ├─ Emit error
        ├─ Emit update     │  event           │  event
        │  event           │                   │
        └─ Continue        ├─ Emit            └─ Continue
           next cycle      │  uncertainty       next cycle
                           │  (all indices)
                           ├─ Reset filters
                           │  (_initialized=False)
                           └─ Continue
                              next cycle

Key Points:
  ✓ Errors don't terminate stream
  ✓ Filter state resets on I/O failure
  ✓ Events provide error context
  ✓ Client can decide action
```

---

## Documentation Navigation Graph

```
┌───────────────────────────────────────────────────────────────────┐
│                   DOCUMENTATION FLOW                              │
└───────────────────────────────────────────────────────────────────┘

START
  │
  ├─ New to SSE?
  │  └─ → SSE_QUICK_REFERENCE.md
  │     ├─ Examples
  │     ├─ Quick params
  │     └─ Use cases
  │
  ├─ Need API spec?
  │  └─ → SSE_API_REFERENCE.md
  │     ├─ All parameters
  │     ├─ Status codes
  │     └─ Behavior
  │
  ├─ Want event details?
  │  └─ → SSE_STREAMING_RESPONSE_FORMAT.md
  │     ├─ JSON schemas
  │     ├─ Real examples
  │     └─ Client code
  │
  ├─ Need practical examples?
  │  └─ → SSE_USAGE_EXAMPLES.md
  │     ├─ Real scenarios
  │     ├─ Filter guide
  │     └─ Best practices
  │
  └─ Lost? Start here
     └─ → SSE_DOCUMENTATION_INDEX.md
        ├─ Navigation
        ├─ Links by topic
        └─ Troubleshooting
```

---

## Async Task Execution Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│              ASYNC TASK EXECUTION TIMELINE                        │
└───────────────────────────────────────────────────────────────────┘

Time │ poll_loadcells() Task    │  Event Queue  │ poll_doors() Task
     │ (interval=0.5s)          │               │ (interval=1.0s)
─────┼──────────────────────────┼───────────────┼──────────────────
  0  │ READ loadcells           │               │ READ doors
     │ PROCESS                  │               │
     │ QUEUE update             │ ← update ←    │
  50 │ await sleep(0.5)         │               │
     │                          │               │
 100 │                          │ YIELD ─→      │ QUEUE update
     │                          │  door.update  │
     │ READ loadcells           │               │
     │ PROCESS                  │               │
     │ QUEUE change/uncertainty │ ← change ←    │
 150 │                          │               │
     │ await sleep(0.5)         │               │
     │                          │               │
 200 │ READ loadcells           │               │ await sleep(1.0)
     │ PROCESS                  │               │
     │ QUEUE update             │ ← update ←    │
 250 │                          │ YIELD ─→      │
     │                          │  change       │
     │ await sleep(0.5)         │               │
 300 │                          │               │ READ doors
     │ READ loadcells           │               │
     │ PROCESS                  │               │
     │ QUEUE update             │ ← update ←    │
     │ await sleep(0.5)         │               │ QUEUE update
 400 │                          │               │
     │ READ loadcells           │               │
     │ PROCESS                  │ YIELD ─→      │
     │                          │  update       │

Notes:
  - Tasks run concurrently
  - Each has independent interval
  - Events queued as generated
  - Consumer pulls from queue
```

---

## Security: Anti-Theft Event Handling

```
┌───────────────────────────────────────────────────────────────────┐
│             ANTI-THEFT: UNCERTAINTY DETECTION                     │
└───────────────────────────────────────────────────────────────────┘

Potential Theft Scenarios
  │
  ├─ Scenario 1: Sensor Tampering
  │  ├─ Raw value: "EEEEEE" or "VVVVVV"
  │  ├─ Emit: loadcell.uncertainty (reason="error_state")
  │  ├─ Action: IMMEDIATE ALERT ⚠️
  │  └─ Continue monitoring
  │
  ├─ Scenario 2: Weight Loss
  │  ├─ Raw change: 1000g → 900g (100g reduction)
  │  ├─ Threshold: 50g
  │  ├─ Change detection: 100 > 50 → YES
  │  ├─ Emit: loadcell.change
  │  ├─ Action: INVESTIGATE
  │  └─ Continue monitoring
  │
  ├─ Scenario 3: I/O Board Disconnected
  │  ├─ Communication fails
  │  ├─ Emit: loadcell.uncertainty (reason="io_board_failure")
  │  ├─ Action: IMMEDIATE ALERT 🚨
  │  ├─ Filters reset (prevent stale data)
  │  └─ Continue polling with errors
  │
  └─ Scenario 4: Sensor Malfunction
     ├─ Multiple read failures
     ├─ Emit: loadcell.uncertainty
     ├─ Action: SERVICE ALERT
     └─ Item potentially at risk

Recommended Client Actions:
  Event: loadcell.uncertainty (io_board_failure)
    → LOCK DOWN SYSTEM
    → Alert security
    → Log incident

  Event: loadcell.uncertainty (error_state)
    → Check sensor hardware
    → Alert maintenance

  Event: loadcell.change (large threshold breach)
    → Verify transaction
    → Review camera footage
    → Check inventory
```

---

## Configuration Best Practices

```
┌───────────────────────────────────────────────────────────────────┐
│              OPTIMAL CONFIGURATION PATTERNS                       │
└───────────────────────────────────────────────────────────────────┘

ANTI-THEFT (Sensitive):
  /sse?streams=loadcells
      &loadcell_interval=0.1    (10 Hz)
      &filter_method=exponential
      &filter_alpha=0.2         (light smoothing)
      &threshold=5.0            (low threshold)
      &threshold_scope=filtered

WAREHOUSE (Efficiency):
  /sse?streams=loadcells
      &loadcell_interval=2.0    (0.5 Hz)
      &filter_method=exponential
      &filter_alpha=0.5         (heavy smoothing)
      &threshold=50.0           (high threshold)
      &threshold_scope=filtered

ACCESS CONTROL (Standard):
  /sse?streams=doors
      &door_interval=0.5        (2 Hz)

MONITORING (Balanced):
  /sse?streams=loadcells,doors
      &loadcell_interval=0.5
      &door_interval=1.0
      &filter_method=kalman
      &filter_q=0.001
      &filter_r=1.0
      &threshold=10.0
      &threshold_scope=filtered
```

This comprehensive visualization suite provides:
- System architecture overview
- Data flow through components
- State machine diagrams
- Decision trees for event emission
- Parameter processing flow
- Filter comparisons
- Threshold scope effects
- Connection lifecycle
- Error handling
- Documentation navigation
- Async execution timing
- Anti-theft scenarios
- Configuration best practices
