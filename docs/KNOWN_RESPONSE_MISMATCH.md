# Known Issue: Serial Response Mismatch

Status: **unresolved hardware/firmware communication issue**  
Tracking: [GitHub issue #3](https://github.com/CHAI-Student/CRK-IO-BOARD/issues/3)

## Summary

CRK-IO-BOARD occasionally receives a valid response for the **previous serial
command** instead of the command most recently transmitted. For example:

```text
TX RQ/IW -> RX RQ/ID
TX RQ/ID -> RX RQ/IW
```

Captured mismatch frames have a valid length, known response shape, and valid
XOR checksum. The received response type consistently matches the immediately
preceding wire TX. This is therefore not explained by ordinary byte corruption
or two application coroutines writing to the port at the same time.

The precise fault domain is not yet proven. Candidates include the IO Board
firmware's command/response state or TX buffer, and the Jetson Orin Nano USB
serial/driver/adapter path. The defect remains present and must not be treated
as resolved by the host-side recovery logic.

## Operational impact

- A mismatch is discarded and the expected response is awaited. In current
  captures no matching response follows, so the first attempt reaches the
  0.5-second header timeout and succeeds only after retry.
- A card-terminal authorization can therefore appear successful upstream while
  the subsequent deadbolt command or `RQ/ID` verification is delayed or fails.
  This is a **leading suspected cause**, not yet a proven sole cause, of cases
  where presenting a card does not open the deadbolt.
- Loadcell `RQ/IW` and IO-status `RQ/ID` responses can be exchanged. This is a
  leading suspected transport-level cause of the observed loadcell raw SSE
  anomalies, alongside the separately documented firmware sign-glitch issue.
- Increasing the inter-command gap reduces occurrence but lowers serial
  throughput and does not eliminate the defect.

## Host-side mitigations already implemented

- A single serial mutex owns the complete request/response transaction.
- An unexpected CMD/SUBCMD frame is logged and discarded without immediately
  retransmitting; the transaction retains ownership while awaiting its match.
- Timeout retry and stale-input draining are instrumented.
- `RQ/IW` wire transmissions are limited to a minimum 0.75-second interval.
- `/health` is read-only and no longer issues deadbolt control or error-clear
  commands.
- `/deadbolt` holds an operation lock from `MC/DC` through settle and `RQ/ID`
  verification.
- Logs include transaction IDs, prior TX type, TX-to-TX and RX-to-TX gaps,
  complete frame hex, shape, length, and checksum validity.
- `IO_BOARD__SERIAL__INTER_COMMAND_GAP` can enforce a diagnostic RX-to-next-TX
  quiet interval. It defaults to `0` and is not a root-cause fix.

## Timing experiment (2026-08-10)

With a raw loadcell SSE subscriber active:

| Minimum RX-to-next-TX gap | Observation |
|---|---|
| 0.1 s | 6 mismatches in about 2 minutes |
| 0.2 s | 6 mismatches in about 4 minutes |
| 0.5 s | 2 mismatches in about 7.5 minutes / about 900 transactions |

Both mismatches in the 0.5-second run occurred with a measured
`rx_to_tx_gap_ms=500.000`. The delay is therefore an effective rate-reduction
experiment, but not a reliable production solution. Each captured mismatch
caused the timeout; the timeout occurred after the wrong response and does not
explain the lower mismatch rate.

## Recommended root-cause correction

When the IO Board or serial transport is revisited:

1. Capture Jetson-side UART/USB traffic with an independent serial analyzer to
   distinguish bytes on the wire from bytes delivered to the application.
2. Assign a sequence number to MCU events: complete RX, handler start, response
   frame creation, TX start, and TX complete.
3. On complete command reception, copy CMD/SUBCMD and request data into an
   immutable per-request context. Do not build the response from a mutable
   global current/previous-command variable.
4. Build CMD/SUBCMD and payload into a dedicated response frame, then keep its
   TX buffer unchanged until UART interrupt/DMA transmission completes.
5. Prevent a later RX interrupt or handler from overwriting the in-flight
   command state or response buffer.
6. Inspect firmware timeout, retry, cache, and resend paths for reuse of the
   previous response.
7. Validate with a controlled alternating `RQ/ID` and `RQ/IW` soak test and
   require zero mismatches before removing host recovery.

## Diagnosis

Search service logs for:

```text
Unexpected response CMD/SUBCMD
Serial response timeout
Serial transaction recovered
```

The most useful fields are `expected`, `got`, `previous_tx`, `tx_gap_ms`,
`rx_to_tx_gap_ms`, `rx_checksum`, and `rx_hex`. Preserve the surrounding logs
and attach them to issue #3. Do not hide the problem by increasing timeouts:
that only delays recovery and card/deadbolt feedback.

