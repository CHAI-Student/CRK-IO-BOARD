from fastapi import APIRouter, Request

import logging

from pydantic import BaseModel, Field

from io_board import recording


logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/start", summary="Start Recording")
async def start_recording(request: Request):
    """
    Start the recording process.
    """
    loadcells_recording_service: recording.RecordingService = request.app.state.recording_services["loadcells"]
    await loadcells_recording_service.start_recording()
    logger.info("Recording started.")
    return {"status": "recording started"}

@router.post("/stop", summary="Stop Recording")
async def stop_recording(request: Request):
    """
    Stop the recording process.
    """
    loadcells_recording_service: recording.RecordingService = request.app.state.recording_services["loadcells"]
    await loadcells_recording_service.stop_recording()
    logger.info("Recording stopped.")
    return {"status": "recording stopped"}

class RecordingItem(BaseModel):
    loadcells: list[str] = Field(..., description="Recorded loadcell data", examples=[
        ["+01234", "-00567", "+00000", "+02345", "-01234", "+03456", "+04567", "-02345", "+06789", "-03456"],
        ["+00001", "+00002", "+00003", "+00004", "+00005", "+00006", "+00007", "+00008", "+00009", "+00010"]
    ])
    timestamp: str = Field(..., description="Timestamp of the recorded data", examples=[
        "2024-01-01T12:00:00Z",
        "2024-06-15T08:30:45Z"
    ])

def unix_to_iso8601(timestamp: float) -> str:
    """Convert a UNIX timestamp to ISO 8601 format."""
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

class RecordingDataResponse(BaseModel):
    logs: list[RecordingItem]

@router.get("/data", summary="Get Recorded Data", responses={200: {"model": RecordingDataResponse}})
async def get_recorded_data(request: Request) -> RecordingDataResponse:
    """
    Retrieve the recorded data.

    Returns:
        RecordingDataResponse: The recorded data with timestamps.
    
    Note:
        Timestamps are returned in ISO 8601 format (UTC).
    """
    logger.info("Retrieving recorded data.")
    loadcells_recording_service: recording.RecordingService = request.app.state.recording_services["loadcells"]
    recordings = await loadcells_recording_service.retrieve_recording()
    logs = [RecordingItem(loadcells=rec.data, timestamp=unix_to_iso8601(rec.timestamp)) for rec in recordings]
    
    return RecordingDataResponse(logs=logs)