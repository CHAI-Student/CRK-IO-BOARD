"""머신 제어 router — health check, deadbolt, door, loadcell, IO status.

주의: 엔드포인트에 description= 이 없는 경우 함수 docstring이 OpenAPI
description으로 노출되므로 해당 docstring은 영어로 유지한다.
Pydantic 응답 모델의 docstring도 같은 이유로 영어를 유지한다.
"""

import asyncio
import logging
import re
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services import error_state_mgmt
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
    door: Literal["HEALTHY", "UNHEALTHY"]


# 정상 loadcell 판독값 형식: 부호 + 5자리 숫자 (예: "+00123")
LOADCELL_PATTERN = re.compile(r"^(\+|-)\d{5}$")

# MCDC 응답은 명령 echo이므로 actuator의 실제 상태 반영은 잠시 기다린 뒤
# RQID로 확인한다. 테스트에서는 이 상수만 낮춰 동시성 검증을 빠르게 한다.
DEADBOLT_SETTLE_SECONDS = 0.5


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
async def get_health(request: Request) -> HealthResponse:
    """IO board의 door/loadcell/deadbolt health 상태를 판정한다."""
    error_state_management_service: error_state_mgmt.ErrorStateManagementService = request.app.state.recording_services["error_state_management"]

    # door: error state management 서비스의 판정을 따른다 (3분 열림 기준)
    door_status = "HEALTHY"
    if not await error_state_management_service.door_error():
        door_status = "UNHEALTHY"

    # loadcell: 형식(부호+5자리)과 범위(기본 ±40000g, config로 조정 가능)를
    # 모두 검사
    health_cfg = request.app.state.settings.health
    loadcells_status = "HEALTHY"
    try:
        loadcells = await commands.get_loadcells()
        if not all(map(lambda x: LOADCELL_PATTERN.fullmatch(x) is not None, loadcells)):
            loadcells_status = "UNHEALTHY"
        elif not all(
            map(
                lambda x: health_cfg.loadcell_min_grams
                <= int(x)
                <= health_cfg.loadcell_max_grams,
                loadcells,
            )
        ):
            loadcells_status = "UNHEALTHY"
    except Exception:
        # CancelledError는 삼키지 않고 전파한다 — shutdown 강제취소 시
        # serial 명령을 계속 수행하는 좀비 요청을 만들지 않기 위함 (R-3)
        loadcells_status = "UNHEALTHY"

    # deadbolt: RQID와 최근 제어의 반영 여부만 읽어서 판정한다.
    # RQER는 timestamp 없는 누적 FIFO라 과거 오류와 현재 고장을 구분할 수
    # 없으므로 health 판정에 사용하지 않는다. MCEZ/MCDC 역시 health에서
    # 수행하지 않아 이 endpoint를 완전한 read-only probe로 유지한다.
    deadbolt_status = "HEALTHY"
    try:
        if not await error_state_management_service.deadbolt_error():
            deadbolt_status = "UNHEALTHY"

        io_status = await commands.get_status()
        # door가 열린 채로 deadbolt가 잠겨 있던 상태는 비정상
        if (
            io_status["deadbolt"] == DeadboltState.LOCKED
            and io_status["door"] == DoorState.OPENED
        ):
            deadbolt_status = "UNHEALTHY"
    except Exception:
        # CancelledError는 삼키지 않고 전파한다 (R-3, 위와 동일)
        deadbolt_status = "UNHEALTHY"

    return HealthResponse(
        deadbolt=deadbolt_status,
        loadcells=loadcells_status,
        door=door_status
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
    """현재 deadbolt 잠금 상태를 조회한다."""
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
async def set_deadbolt(request: Request, deadbolt_request: DeadboltRequest) -> DeadboltResponse:
    """deadbolt를 제어한다.

    Args:
        deadbolt_request: 원하는 상태가 담긴 deadbolt 제어 요청

    Returns:
        command 실행 후의 실제 deadbolt 상태
    """
    error_state_management_service: error_state_mgmt.ErrorStateManagementService = request.app.state.recording_services["error_state_management"]
    operation_lock: asyncio.Lock = request.app.state.deadbolt_operation_lock

    # serial mutex는 개별 MCDC/RQID frame만 보호한다. 이 operation lock은
    # 다른 /deadbolt 요청(및 향후 self-test)이 settle 구간에 끼어들어 목표
    # 상태를 덮어쓰지 못하도록 MCDC부터 RQID 확인까지 전체를 보호한다.
    async with operation_lock:
        # error state management에 제어 요청을 기록 (health 판정용)
        await error_state_management_service.set_deadbolt_action(
            deadbolt_request.action
        )
        await commands.set_deadbolt(deadbolt_request.action)

        # 상태 변화가 반영될 시간을 확보하기 위한 지연
        await asyncio.sleep(DEADBOLT_SETTLE_SECONDS)

        # 실제 deadbolt 상태를 IO status로 재확인해 반환
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
    # 현재 door 열림/닫힘 상태 조회.
    # (이 route는 description= 미지정이라 아래 docstring이 OpenAPI에
    # 노출되므로 영어 docstring을 유지한다.)
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
    """loadcell 무게 판독값을 조회한다 (throttle/sanitizer 적용)."""
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
    """door 및 deadbolt IO status를 조회한다."""
    io_status = await commands.get_status()
    return IOStatusResponse(
        door=io_status["door"],
        deadbolt=io_status["deadbolt"],
    )
