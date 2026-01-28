from fastapi import APIRouter, Request

import logging

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

@router.get("/data", summary="Get Recorded Data")
async def get_recorded_data(request: Request):
    """
    Retrieve the recorded data.
    """
    logger.info("Retrieving recorded data.")
    loadcells_recording_service: recording.RecordingService = request.app.state.recording_services["loadcells"]
    data = await loadcells_recording_service.retrieve_recording()
    recorded_data = {"logs": data}
    return recorded_data