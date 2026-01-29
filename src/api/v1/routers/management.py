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
    """Initialize the IO Board device."""
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
    """Calibrate IO Board sensors."""
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
    """Get device manufacturing number."""
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
    """
    Set device manufacturing number.

    Args:
        request: Manufacturing number (11 characters)

    Returns:
        Manufacturing number as confirmed by device
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
    """Get device software version."""
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
    """Reboot IO Board device (hard reboot via relay with timer). Device may not reply due to power interrupt."""
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
    """Get device product information."""
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
    """Get device error history."""
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
    """Clear device error log."""
    await commands.clear_errors()
    return SuccessResponse(message="Error log cleared successfully")
