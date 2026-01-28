"""
IO Board Control Service - Main Entry Point.

This module is the main entry point for the IO Board control service.
It loads configuration, sets up logging, and starts the FastAPI server.
"""

import asyncio

from io_board import recording
from io_board.api.main import serve_api
from io_board.config import load_config
from io_board.logging_config import setup_logging, get_logger
from io_board.serial_io import configure_serial
from io_board.stream import data_sources, polling_service


async def main() -> None:
    """
    Main application entry point.
    
    Loads configuration from environment variables, sets up logging,
    configures serial communication, and starts the API server.
    """
    # Load configuration from environment
    config = load_config()
    
    # Setup structured logging
    setup_logging(config.api.log_level.upper())
    logger = get_logger(__name__)
    
    logger.info("=" * 60)
    logger.info("IO Board Control Service Starting")
    logger.info("=" * 60)
    
    # Log configuration (without sensitive data)
    logger.info(f"Serial Port: {config.serial.port}")
    logger.info(f"Serial Baudrate: {config.serial.baudrate}")
    logger.info(f"API Host: {config.api.host}")
    logger.info(f"API Port: {config.api.port}")
    logger.info(f"Log Level: {config.api.log_level}")
    
    # Configure serial communication
    configure_serial(config.serial)

    loadcells_data_source = data_sources.LoadCellsDataSource()
    loadcells_polling_service = polling_service.PollingService(
        data_source=loadcells_data_source,
        interval=config.stream.loadcell_poll_interval,
        name="LoadCells",
    )
    io_status_data_source = data_sources.IOStatusDataSource()
    io_status_polling_service = polling_service.PollingService(
        data_source=io_status_data_source,
        interval=config.stream.io_status_poll_interval,
        name="IOStatus",
    )

    polling_services = {
        "loadcells": loadcells_polling_service,
        "io_status": io_status_polling_service,
    }

    loadcells_recording_service = recording.RecordingService(
        polling_service=loadcells_polling_service,
        name="LoadCellsRecording",
    )

    recording_services = {
        "loadcells": loadcells_recording_service,
    }

    # Start polling services
    await loadcells_polling_service.start()
    await io_status_polling_service.start()

    # Start recording services
    await loadcells_recording_service.start()

    # Start API server
    try:
        await serve_api(config.api, polling_services, recording_services)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=e)
        raise
    finally:
        # Stop recording services
        await loadcells_recording_service.stop()
        # Stop polling services
        await loadcells_polling_service.stop()
        await io_status_polling_service.stop()
        logger.info("IO Board Control Service Stopped")


if __name__ == "__main__":
    asyncio.run(main())


