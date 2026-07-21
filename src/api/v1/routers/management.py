"""관리(management) router — 초기화, calibration, 제조번호, 에러 로그, 재부팅.

모든 route가 summary/description을 명시하므로 함수 docstring은 OpenAPI에
노출되지 않는다.
"""

from fastapi import APIRouter

from services.io_board import commands
from services.io_board.io_types import (
    ErrorItem,
    ErrorListResponse,
    ManufacturingNumberRequest,
    ManufacturingNumberResponse,
    ProductInfoResponse,
    SoftwareVersionResponse,
    StandardErrorResponse,
    SuccessResponse,
)

router = APIRouter(
    tags=["Management"],
)


@router.post(
    "/init",
    response_model=SuccessResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Initialize IO Board",
    description="Initialize the IO Board device. Should be called after device power-on or reset.",
)
async def initialize_device() -> SuccessResponse:
    """IO Board 디바이스를 초기화한다."""
    await commands.initialize()
    return SuccessResponse(message="IO Board initialized successfully")


@router.post(
    "/calibrate",
    response_model=SuccessResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Calibrate sensors",
    description="Calibrate all loadcell weight sensors. Device should be unloaded before calibration.",
)
async def calibrate_loadcells() -> SuccessResponse:
    """loadcell 센서를 calibrate한다 (무부하 상태 필요)."""
    await commands.calibrate()
    return SuccessResponse(message="Calibration completed successfully")


@router.get(
    "/manufacturing-number",
    response_model=ManufacturingNumberResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get manufacturing number",
    description="Retrieve the device manufacturing/product ID (11 alphanumeric characters).",
)
async def get_manufacturing_number() -> ManufacturingNumberResponse:
    """디바이스 제조번호를 조회한다."""
    info = await commands.get_product_info()
    return ManufacturingNumberResponse(manufacturing_number=info["product_id"])


@router.post(
    "/manufacturing-number",
    response_model=ManufacturingNumberResponse,
    responses={
        422: {"description": "Invalid manufacturing number format"},
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        },
    },
    summary="Set manufacturing number",
    description="Set the device manufacturing/product ID (11 alphanumeric characters).",
)
async def set_manufacturing_number(
    request: ManufacturingNumberRequest,
) -> ManufacturingNumberResponse:
    """디바이스 제조번호를 설정한다.

    Args:
        request: 제조번호 (11자)

    Returns:
        디바이스가 확인(echo back)한 제조번호
    """
    result = await commands.set_manufacturing_number(request.manufacturing_number)
    return ManufacturingNumberResponse(manufacturing_number=result)


@router.get(
    "/software-version",
    response_model=SoftwareVersionResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get software version",
    description="Retrieve the device software/firmware version.",
)
async def get_software_version() -> SoftwareVersionResponse:
    """디바이스 소프트웨어/펌웨어 버전을 조회한다."""
    info = await commands.get_product_info()
    return SoftwareVersionResponse(sw_version=info["sw_version"])


@router.post(
    "/reboot",
    response_model=SuccessResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Reboot device",
    description="Reboot the IO Board device (hard reboot via relay with timer). Device will be unavailable during restart and may not reply due to power interrupt.",
)
async def reboot_device() -> SuccessResponse:
    """IO Board를 재부팅한다 (타이머 릴레이 하드 재부팅). 전원 차단으로 응답이 없을 수 있다."""
    await commands.reboot()
    return SuccessResponse(message="Device reboot initiated")


@router.get(
    "/product-info",
    response_model=ProductInfoResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get product information",
    description="Retrieve device manufacturing information including product ID and software version.",
)
async def get_product_info() -> ProductInfoResponse:
    """디바이스 제조 정보(product ID + 버전)를 조회한다."""
    info = await commands.get_product_info()
    return ProductInfoResponse(
        product_id=info["product_id"],
        sw_version=info["sw_version"],
    )


@router.get(
    "/errors",
    response_model=ErrorListResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Get error list",
    description="Retrieve device error history (up to 4 error codes).",
)
async def get_errors() -> ErrorListResponse:
    """디바이스 에러 히스토리를 조회한다 (최대 4건)."""
    errors = await commands.get_errors()
    return ErrorListResponse(errors=[ErrorItem(code=err) for err in errors])


@router.delete(
    "/errors",
    response_model=SuccessResponse,
    responses={
        500: {
            "model": StandardErrorResponse,
            "description": "Device or communication error",
        }
    },
    summary="Clear error log",
    description="Clear all error codes from the device error history.",
)
async def clear_errors() -> SuccessResponse:
    """디바이스 에러 로그를 비운다."""
    await commands.clear_errors()
    return SuccessResponse(message="Error log cleared successfully")
