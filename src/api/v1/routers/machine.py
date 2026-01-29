import logging
import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.io_board import commands
from services.io_board.io_types import (
    DeadboltAction,
    DeadboltState,
    DoorState,
    StandardErrorResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Machine"],
)


################
# HEALTH CHECK #
################


class HealthResponse(BaseModel):
    """IO board health status response."""

    deadbolt: Literal["HEALTHY", "UNHEALTHY"]
    loadcells: Literal["HEALTHY", "UNHEALTHY"]


LOADCELL_PATTERN = re.compile(r"^(\+|-)\d{5}$")


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get IO board health status",
    description="Check if the IO board is reachable and functioning properly.",
)
async def get_health() -> HealthResponse:
    """Get IO board health status."""
    loadcells_status = "HEALTHY"
    try:
        loadcells = await commands.get_loadcells()
        if not all(map(lambda x: not LOADCELL_PATTERN.fullmatch(x) is None, loadcells)):
            loadcells_status = "UNHEALTHY"
        elif not all(map(lambda x: -40000 <= int(x) <= 40000, loadcells)):
            loadcells_status = "UNHEALTHY"
    except:
        loadcells_status = "UNHEALTHY"

    deadbolt_status = "HEALTHY"
    try:
        await commands.clear_errors()
        prev_status = await commands.get_status()
        await commands.set_deadbolt(
            DeadboltAction.OPEN
            if prev_status["deadbolt"] == DeadboltState.UNLOCK
            else DeadboltAction.CLOSE
        )
        errors = await commands.get_errors()
        if not all(map(lambda x: x == "    " or x == "0000", errors)):
            deadbolt_status = "UNHEALTHY"
    except:
        deadbolt_status = "UNHEALTHY"

    return HealthResponse(
        deadbolt=deadbolt_status,
        loadcells=loadcells_status,
    )


############
# DEADBOLT #
############


class DeadboltRequest(BaseModel):
    """Request model for deadbolt control."""

    action: DeadboltAction = Field(
        ..., description="Desired deadbolt state", examples=["OPEN", "CLOSE"]
    )


class DeadboltResponse(BaseModel):
    """Response model for deadbolt control."""

    state: DeadboltState = Field(
        ..., description="Current deadbolt state", examples=["UNLOCK", "LOCKED"]
    )


@router.get(
    "/deadbolt",
    response_model=DeadboltResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get deadbolt status",
    description="Get current status of the door deadbolt sensor.",
)
async def get_deadbolt() -> DeadboltResponse:
    """Get current deadbolt lock status."""
    io_status = await commands.get_status()
    return DeadboltResponse(state=io_status["deadbolt"])


@router.post(
    "/deadbolt",
    response_model=DeadboltResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Control door deadbolt",
    description="Open or close the door deadbolt lock. Returns the actual state after command execution.",
)
async def set_deadbolt(request: DeadboltRequest) -> DeadboltResponse:
    """
    Control door deadbolt lock.

    Args:
        request: Deadbolt control request with desired state

    Returns:
        Current deadbolt state after command execution
    """
    await commands.set_deadbolt(request.action)

    # Also get full IO status to verify deadbolt state
    io_status = await commands.get_status()
    return DeadboltResponse(state=io_status["deadbolt"])


########
# DOOR #
########


class DoorResponse(BaseModel):
    """Response model for door status."""

    state: DoorState = Field(
        ..., description="Current door state", examples=["OPENED", "CLOSED"]
    )


@router.get(
    "/door",
    response_model=DoorResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
)
async def get_door() -> DoorResponse:
    """Get current door open/closed status."""
    io_status = await commands.get_status()
    return DoorResponse(state=io_status["door"])


#############
# LOADCELLS #
#############


class LoadCellsResponse(BaseModel):
    """Response model for loadcell readings."""

    loadcells: list[str] = Field(
        ...,
        description="Array of 10 loadcell readings (6 chars each: +/-XXXXX or EEEEEE/VVVVVV for errors)",
        min_length=10,
        max_length=10,
        examples=[
            [
                "+12345",
                "-00123",
                "+99999",
                "-12345",
                "+00000",
                "-00001",
                "+54321",
                "-99999",
                "+11111",
                "-22222",
            ]
        ],
    )


@router.get(
    "/loadcells",
    response_model=LoadCellsResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get loadcell readings",
    description="Get current weight readings from all 10 loadcell sensors.",
)
async def handle_loadcells() -> LoadCellsResponse:
    """Get loadcell weight readings."""
    loadcells = await commands.get_loadcells()
    return LoadCellsResponse(loadcells=loadcells)


##########
# STATUS #
##########


class IOStatusResponse(BaseModel):
    """Response model for IO status."""

    door: str = Field(
        ..., description="Door sensor status", examples=["OPENED", "CLOSED"]
    )
    deadbolt: str = Field(
        ..., description="Deadbolt sensor status", examples=["OPENED", "LOCKED"]
    )


@router.get(
    "/status",
    response_model=IOStatusResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get IO status",
    description="Get current status of door and deadbolt sensors.",
)
async def handle_status() -> IOStatusResponse:
    """Get door and deadbolt IO status."""
    io_status = await commands.get_status()
    return IOStatusResponse(
        door=io_status["door"],
        deadbolt=io_status["deadbolt"],
    )
