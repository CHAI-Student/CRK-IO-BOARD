"""recording router — loadcell 기록 시작/정지/조회.

주의: 이 router의 route들은 description= 을 지정하지 않아 함수 docstring이
OpenAPI description으로 노출된다. 따라서 docstring은 영어로 유지한다.
"""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.time_utils import unix_to_iso8601
from services import recording


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recording", tags=["Recording"])

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