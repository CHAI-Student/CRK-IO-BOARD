import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from io_board.events import LoadcellChangeDetector
from io_board.exceptions import IOBoardError
from io_board.filters import FilterMethod, ThresholdScope
from io_board.io_types import (
    DoorUpdateEvent,
    LoadcellChangeEvent,
    LoadcellUncertaintyEvent,
    LoadcellUpdateEvent,
    StandardErrorResponse,
)
from io_board.stream import stream_queues

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/sse",
    responses={
        200: {
            "description": "Unified Server-Sent Events stream with 5 event types",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "type": "object",
                        "description": "Server-Sent Events stream with 5 possible event types",
                        "oneOf": [
                            {
                                "type": "object",
                                "title": "loadcell.update",
                                "description": "Periodic loadcell readings (sent every loadcell_interval seconds)",
                                "properties": {
                                    "timestamp": {
                                        "type": "string",
                                        "format": "date-time",
                                        "example": "2026-01-17T14:30:45.123456",
                                    },
                                    "raw_values": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 10,
                                        "maxItems": 10,
                                        "example": [
                                            "+12345",
                                            "+00123",
                                            "-00456",
                                            "+99999",
                                            "+00000",
                                            "+11111",
                                            "+22222",
                                            "+33333",
                                            "+44444",
                                            "+55555",
                                        ],
                                    },
                                    "filtered_values": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 10,
                                        "maxItems": 10,
                                        "example": [
                                            "+12345",
                                            "+00123",
                                            "-00456",
                                            "+99999",
                                            "+00000",
                                            "+11111",
                                            "+22222",
                                            "+33333",
                                            "+44444",
                                            "+55555",
                                        ],
                                    },
                                    "filter_method": {
                                        "type": "string",
                                        "enum": ["none", "exponential", "kalman"],
                                        "example": "none",
                                    },
                                },
                                "required": [
                                    "timestamp",
                                    "raw_values",
                                    "filtered_values",
                                    "filter_method",
                                ],
                            },
                            {
                                "type": "object",
                                "title": "loadcell.change",
                                "description": "Threshold breach detection (anti-theft event)",
                                "properties": {
                                    "timestamp": {
                                        "type": "string",
                                        "format": "date-time",
                                        "example": "2026-01-17T14:30:45.456789",
                                    },
                                    "changed_indices": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                        "example": [0, 3, 7],
                                    },
                                    "old_values": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "example": [12340.0, 99995.0, 33330.0],
                                    },
                                    "new_values": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "example": [12355.0, 99980.0, 33350.0],
                                    },
                                    "deltas": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "example": [15.0, 15.0, 20.0],
                                    },
                                    "threshold": {
                                        "oneOf": [
                                            {"type": "number", "example": 10.0},
                                            {
                                                "type": "array",
                                                "items": {"type": "number"},
                                                "minItems": 10,
                                                "maxItems": 10,
                                            },
                                        ]
                                    },
                                    "threshold_scope": {
                                        "type": "string",
                                        "enum": ["raw", "filtered"],
                                        "example": "filtered",
                                    },
                                },
                                "required": [
                                    "timestamp",
                                    "changed_indices",
                                    "old_values",
                                    "new_values",
                                    "deltas",
                                    "threshold",
                                    "threshold_scope",
                                ],
                            },
                            {
                                "type": "object",
                                "title": "loadcell.uncertainty",
                                "description": "Security event - sensor errors or I/O board failure",
                                "properties": {
                                    "timestamp": {
                                        "type": "string",
                                        "format": "date-time",
                                        "example": "2026-01-17T14:30:45.678901",
                                    },
                                    "affected_indices": {
                                        "type": "array",
                                        "items": {
                                            "type": "integer",
                                            "minimum": 0,
                                            "maximum": 9,
                                        },
                                        "example": [2, 5, 8],
                                    },
                                    "reason": {
                                        "type": "string",
                                        "enum": ["error_state", "io_board_failure"],
                                        "example": "error_state",
                                    },
                                    "details": {
                                        "type": "object",
                                        "example": {
                                            "error_values": [
                                                "EEEEEE",
                                                "VVVVVV",
                                                "EEEEEE",
                                            ]
                                        },
                                    },
                                },
                                "required": [
                                    "timestamp",
                                    "affected_indices",
                                    "reason",
                                    "details",
                                ],
                            },
                            {
                                "type": "object",
                                "title": "door.update",
                                "description": "Periodic door and deadbolt status (sent every door_interval seconds)",
                                "properties": {
                                    "timestamp": {
                                        "type": "string",
                                        "format": "date-time",
                                        "example": "2026-01-17T14:30:45.890123",
                                    },
                                    "door": {
                                        "type": "string",
                                        "minLength": 6,
                                        "maxLength": 6,
                                        "example": "CLOSED",
                                    },
                                    "deadbolt": {
                                        "type": "string",
                                        "minLength": 6,
                                        "maxLength": 6,
                                        "example": "CLOSED",
                                    },
                                },
                                "required": ["timestamp", "door", "deadbolt"],
                            },
                            {
                                "type": "object",
                                "title": "error",
                                "description": "Stream-level communication or processing errors",
                                "properties": {
                                    "stream": {
                                        "type": "string",
                                        "enum": ["loadcells", "doors"],
                                        "example": "loadcells",
                                    },
                                    "error_code": {
                                        "type": "string",
                                        "pattern": "^E\\d{4}$",
                                        "example": "E2001",
                                    },
                                    "message": {
                                        "type": "string",
                                        "example": "Serial communication timeout",
                                    },
                                    "details": {"type": "object", "example": {}},
                                },
                                "required": [
                                    "stream",
                                    "error_code",
                                    "message",
                                    "details",
                                ],
                            },
                        ],
                    },
                    "examples": {
                        "loadcell_update_no_filter": {
                            "summary": "Loadcell update with no filtering",
                            "value": {
                                "timestamp": "2026-01-17T14:30:45.123456",
                                "raw_values": [
                                    "+12345",
                                    "+00123",
                                    "-00456",
                                    "+99999",
                                    "+00000",
                                    "+11111",
                                    "+22222",
                                    "+33333",
                                    "+44444",
                                    "+55555",
                                ],
                                "filtered_values": [
                                    "+12345",
                                    "+00123",
                                    "-00456",
                                    "+99999",
                                    "+00000",
                                    "+11111",
                                    "+22222",
                                    "+33333",
                                    "+44444",
                                    "+55555",
                                ],
                                "filter_method": "none",
                            },
                        },
                        "loadcell_update_exponential": {
                            "summary": "Loadcell update with exponential smoothing",
                            "value": {
                                "timestamp": "2026-01-17T14:30:45.234567",
                                "raw_values": [
                                    "+12355",
                                    "+00125",
                                    "-00460",
                                    "+99998",
                                    "+00001",
                                    "+11112",
                                    "+22225",
                                    "+33335",
                                    "+44445",
                                    "+55556",
                                ],
                                "filtered_values": [
                                    "+12348",
                                    "+00123",
                                    "-00457",
                                    "+99998",
                                    "+00000",
                                    "+11111",
                                    "+22223",
                                    "+33334",
                                    "+44444",
                                    "+55555",
                                ],
                                "filter_method": "exponential",
                            },
                        },
                        "loadcell_change_single_threshold": {
                            "summary": "Threshold breach with single broadcast threshold",
                            "value": {
                                "timestamp": "2026-01-17T14:30:45.456789",
                                "changed_indices": [0, 3, 7],
                                "old_values": [12340.0, 99995.0, 33330.0],
                                "new_values": [12355.0, 99980.0, 33350.0],
                                "deltas": [15.0, 15.0, 20.0],
                                "threshold": 10.0,
                                "threshold_scope": "filtered",
                            },
                        },
                        "loadcell_change_per_loadcell": {
                            "summary": "Threshold breach with per-loadcell thresholds",
                            "value": {
                                "timestamp": "2026-01-17T14:30:45.567890",
                                "changed_indices": [1, 5],
                                "old_values": [123.0, 456.0],
                                "new_values": [138.0, 476.0],
                                "deltas": [15.0, 20.0],
                                "threshold": [
                                    10.0,
                                    15.0,
                                    12.0,
                                    8.0,
                                    9.0,
                                    18.0,
                                    11.0,
                                    13.0,
                                    14.0,
                                    10.0,
                                ],
                                "threshold_scope": "raw",
                            },
                        },
                        "loadcell_uncertainty_error_state": {
                            "summary": "Uncertainty from sensor error codes",
                            "value": {
                                "timestamp": "2026-01-17T14:30:45.678901",
                                "affected_indices": [2, 5, 8],
                                "reason": "error_state",
                                "details": {
                                    "error_values": ["EEEEEE", "VVVVVV", "EEEEEE"]
                                },
                            },
                        },
                        "loadcell_uncertainty_io_failure": {
                            "summary": "Uncertainty from I/O board communication failure",
                            "value": {
                                "timestamp": "2026-01-17T14:30:45.789012",
                                "affected_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
                                "reason": "io_board_failure",
                                "details": {
                                    "error_code": "E2001",
                                    "message": "Serial communication timeout",
                                    "details": {},
                                },
                            },
                        },
                        "door_update_closed": {
                            "summary": "Door and deadbolt both closed/locked",
                            "value": {
                                "timestamp": "2026-01-17T14:30:45.890123",
                                "door": "CLOSED",
                                "deadbolt": "CLOSED",
                            },
                        },
                        "door_update_open": {
                            "summary": "Door and deadbolt both open/unlocked",
                            "value": {
                                "timestamp": "2026-01-17T14:30:46.901234",
                                "door": "OPENED",
                                "deadbolt": "OPENED",
                            },
                        },
                        "error_event": {
                            "summary": "Communication error event",
                            "value": {
                                "stream": "loadcells",
                                "error_code": "E2001",
                                "message": "Serial communication timeout",
                                "details": {},
                            },
                        },
                    },
                }
            },
        },
        422: {"model": StandardErrorResponse, "description": "Invalid parameters"},
    },
    response_model=None,
    summary="Unified SSE stream for loadcells and door status",
    description="""Server-Sent Events stream with configurable data sources and filtering.
    
    **Event Types:**
    - `loadcell.update`: Periodic loadcell readings (filtered and raw)
    - `loadcell.change`: Threshold breach detection events
    - `loadcell.uncertainty`: Error states or parse failures (anti-theft)
    - `door.update`: Periodic door/deadbolt status
    - `error`: Stream-level errors
    
    **Example Usage:**
    - Single stream: `/sse?streams=loadcells&loadcell_interval=0.5`
    - Dual stream: `/sse?streams=loadcells,doors&loadcell_interval=0.2&door_interval=1.0`
    - With filtering: `/sse?streams=loadcells&filter_method=exponential&filter_alpha=0.3`
    - With thresholds: `/sse?streams=loadcells&threshold=10.0&threshold_scope=filtered`
    """,
    tags=["Streaming"],
)
async def handle_unified_sse(
    request: Request,
    streams: str = Query(
        ...,
        description="Comma-separated list of streams to enable (loadcells, doors)",
        example="loadcells,doors",
    ),
    loadcell_interval: float = Query(
        default=0.5,
        ge=0.1,
        le=10.0,
        description="Polling interval for loadcell updates in seconds (minimum 0.1s)",
        example=0.5,
    ),
    door_interval: float = Query(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Polling interval for door status updates in seconds (minimum 0.1s)",
        example=1.0,
    ),
    filter_method: FilterMethod = Query(
        default=FilterMethod.NONE,
        description="Filtering method for loadcell values (none, exponential, kalman)",
        example="exponential",
    ),
    filter_alpha: float = Query(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Alpha parameter for exponential smoothing (0.0=max smoothing, 1.0=no smoothing)",
        example=0.3,
    ),
    filter_q: float = Query(
        default=0.001,
        gt=0.0,
        description="Process noise covariance (Q) for Kalman filter",
        example=0.001,
    ),
    filter_r: float = Query(
        default=1.0,
        gt=0.0,
        description="Measurement noise covariance (R) for Kalman filter",
        example=1.0,
    ),
    threshold: str = Query(
        default="0.0",
        description="Threshold for change detection. Single value (broadcast to all 10) or comma-separated list of 10 values",
        example="5.0",
    ),
    threshold_scope: ThresholdScope = Query(
        default=ThresholdScope.FILTERED,
        description="Apply threshold to raw or filtered values",
        example="filtered",
    ),
) -> JSONResponse | StreamingResponse:
    """
    Unified SSE endpoint for streaming loadcell and door status.

    Supports multiple concurrent data streams with independent intervals,
    configurable filtering, and threshold-based change detection.
    """
    # Parse and validate streams parameter
    enabled_streams = [s.strip() for s in streams.split(",") if s.strip()]
    valid_streams = {"loadcells", "doors"}
    invalid_streams = set(enabled_streams) - valid_streams

    if not enabled_streams:
        logger.error("Empty streams parameter provided")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "E4002",
                "message": "At least one stream must be specified",
                "details": {"valid_streams": list(valid_streams)},
            },
        )

    if invalid_streams:
        logger.error(f"Invalid stream names: {invalid_streams}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "E4003",
                "message": f"Invalid stream names: {', '.join(invalid_streams)}",
                "details": {
                    "valid_streams": list(valid_streams),
                    "invalid_streams": list(invalid_streams),
                },
            },
        )

    # Parse threshold parameter
    threshold_values = []
    threshold_parts = [t.strip() for t in threshold.split(",") if t.strip()]

    if len(threshold_parts) == 1:
        # Single value - broadcast to all 10 loadcells
        try:
            single_threshold = float(threshold_parts[0])
            threshold_values = [single_threshold] * 10
        except ValueError:
            logger.error(f"Invalid threshold value: {threshold_parts[0]}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error_code": "E4004",
                    "message": "Threshold must be a valid number",
                    "details": {"provided": threshold_parts[0]},
                },
            )
    elif len(threshold_parts) == 10:
        # Per-loadcell thresholds
        try:
            threshold_values = [float(t) for t in threshold_parts]
        except ValueError as e:
            logger.error(f"Invalid threshold values: {e}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error_code": "E4005",
                    "message": "All threshold values must be valid numbers",
                    "details": {"provided": threshold_parts},
                },
            )
    else:
        logger.error(
            f"Invalid threshold count: {len(threshold_parts)} (expected 1 or 10)"
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "E4006",
                "message": "Threshold must be a single value or exactly 10 comma-separated values",
                "details": {
                    "provided_count": len(threshold_parts),
                    "expected": "1 or 10",
                },
            },
        )

    logger.info(
        f"Starting unified SSE stream: streams={enabled_streams} "
        f"loadcell_interval={loadcell_interval} door_interval={door_interval} "
        f"filter_method={filter_method} threshold_scope={threshold_scope}"
    )

    async def unified_event_generator():
        """Generate multiplexed SSE events from enabled streams."""
        stop_flag = request.app.state.stop_event
        event_queue = asyncio.Queue()
        tasks = []

        # Create change detector if loadcells stream enabled
        loadcells_queue = None
        detector = None
        if "loadcells" in enabled_streams:
            loadcells_queue = stream_queues.Queue() # TODO: Pass actual loadcell queue from commands module
            await request.app.state.polling_services["loadcells"].subscribe(loadcells_queue)
            detector = LoadcellChangeDetector(
                filter_method=filter_method,
                thresholds=threshold_values,
                threshold_scope=threshold_scope,
                alpha=filter_alpha,
                q=filter_q,
                r=filter_r,
            )
            poll_loadcells = make_poll_loadcells(
                request,
                loadcells_queue,
                event_queue,
                detector,
            )
            tasks.append(asyncio.create_task(poll_loadcells()))

        io_status_queue = None
        if "doors" in enabled_streams:
            io_status_queue = stream_queues.Queue() # TODO: Pass actual I/O status queue from commands module
            await request.app.state.polling_services["io_status"].subscribe(io_status_queue)
            poll_doors = make_poll_doors(
                request,
                io_status_queue,
                event_queue,
            )
            tasks.append(asyncio.create_task(poll_doors()))

        try:
            # Consume events from queue and yield SSE formatted data
            while not stop_flag.is_set():
                if await request.is_disconnected():
                    logger.info("Client disconnected from unified SSE stream")
                    break

                # Wait for next event with timeout to check disconnect status
                try:
                    event_name, event_data = await asyncio.wait_for(
                        event_queue.get(), timeout=0.5
                    )
                    yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    # No event available, continue to check disconnect
                    continue
                except asyncio.CancelledError:
                    logger.info("Unified SSE generator cancelled")
                    raise

        finally:
            if loadcells_queue:
                await request.app.state.polling_services["loadcells"].unsubscribe(
                    loadcells_queue
                )
                loadcells_queue.shutdown()
            if io_status_queue:
                await request.app.state.polling_services["io_status"].unsubscribe(
                    io_status_queue
                )
                io_status_queue.shutdown()

            # Cancel all polling tasks
            for task in tasks:
                task.cancel()

            # Wait for tasks to complete cancellation
            await asyncio.gather(*tasks, return_exceptions=True)

            logger.info(f"Unified SSE stream ended: streams={enabled_streams}")

    return StreamingResponse(
        unified_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def make_poll_loadcells(
    request: Request,
    loadcells_queue: asyncio.Queue,
    event_queue: asyncio.Queue,
    detector: LoadcellChangeDetector,
):
    async def poll_loadcells():
        """Poll loadcell data and generate events."""
        while not request.app.state.stop_event.is_set():
            if await request.is_disconnected():
                break

            try:
                raw_values: list[str] = await loadcells_queue.get()
                timestamp = datetime.utcnow().isoformat()

                # Process values through detector
                (
                    filtered_strings,
                    filtered_numerics,
                    changed_indices,
                    change_details,
                ) = detector.process(raw_values)

                # Check for uncertainties
                uncertain_indices = detector.detect_uncertainties(
                    raw_values, filtered_numerics
                )

                # Always send update event
                update_event = LoadcellUpdateEvent(
                    timestamp=timestamp,
                    raw_values=raw_values,
                    filtered_values=filtered_strings,
                    filter_method=detector.filter_method.value,
                )
                await event_queue.put(("loadcell.update", update_event.model_dump()))

                # Send change event if threshold exceeded
                if changed_indices:
                    change_event = LoadcellChangeEvent(
                        timestamp=timestamp,
                        changed_indices=changed_indices,
                        old_values=change_details["old_values"],
                        new_values=change_details["new_values"],
                        deltas=change_details["deltas"],
                        threshold=(
                            detector.thresholds[0]
                            if len(set(detector.thresholds)) == 1
                            else detector.thresholds
                        ),
                        threshold_scope=detector.threshold_scope.value,
                    )
                    await event_queue.put(
                        ("loadcell.change", change_event.model_dump())
                    )

                # Send uncertainty event if errors detected
                if uncertain_indices:
                    error_values = [raw_values[i] for i in uncertain_indices]
                    uncertainty_event = LoadcellUncertaintyEvent(
                        timestamp=timestamp,
                        affected_indices=uncertain_indices,
                        reason="error_state",
                        details={"error_values": error_values},
                    )
                    await event_queue.put(
                        ("loadcell.uncertainty", uncertainty_event.model_dump())
                    )
            except asyncio.CancelledError:
                logger.info("Loadcell polling cancelled")
                raise
            except IOBoardError as e:
                # I/O board failure - reset filter state and send uncertainty for all loadcells
                if detector:
                    detector.reset()

                timestamp = datetime.utcnow().isoformat()
                uncertainty_event = LoadcellUncertaintyEvent(
                    timestamp=timestamp,
                    affected_indices=list(range(10)),
                    reason="io_board_failure",
                    details=e.to_dict(),
                )
                await event_queue.put(
                    ("loadcell.uncertainty", uncertainty_event.model_dump())
                )

                # Also send error event
                await event_queue.put(("error", {"stream": "loadcells", **e.to_dict()}))
                logger.warning(f"Loadcell stream error: {e}")

            except Exception as e:
                # Unexpected error
                logger.error(f"Unexpected error in loadcell stream: {e}", exc_info=e)
                await event_queue.put(
                    (
                        "error",
                        {
                            "stream": "loadcells",
                            "error_code": "E9002",
                            "message": "Unexpected loadcell stream error",
                            "details": {},
                        },
                    )
                )

    return poll_loadcells


def make_poll_doors(
    request: Request,
    io_status_queue: asyncio.Queue,
    event_queue: asyncio.Queue,
):
    async def poll_doors():
        """Poll door status and generate events."""
        while not request.app.state.stop_event.is_set():
            if await request.is_disconnected():
                break
            
            try:
                io_status: dict[str, str] = await io_status_queue.get()
                timestamp = datetime.utcnow().isoformat()
                door_event = DoorUpdateEvent(
                    timestamp=timestamp,
                    door=io_status["door"],
                    deadbolt=io_status["deadbolt"],
                )
                await event_queue.put(("door.update", door_event.model_dump()))
            except asyncio.CancelledError:
                logger.info("Door polling cancelled")
                raise
            except IOBoardError as e:
                # Send error event but don't terminate
                await event_queue.put(("error", {"stream": "doors", **e.to_dict()}))
                logger.warning(f"Door stream error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in door stream: {e}", exc_info=e)
                await event_queue.put(
                    (
                        "error",
                        {
                            "stream": "doors",
                            "error_code": "E9003",
                            "message": "Unexpected door stream error",
                            "details": {},
                        },
                    )
                )

    return poll_doors
