"""
IO Board Control Service - Main Entry Point.

This module is the main entry point for the IO Board control service.
It loads configuration, sets up logging, and starts the FastAPI server.
"""

import asyncio

from io_board.api import serve_api
from io_board.config import load_config
from io_board.logging_config import setup_logging, get_logger
from io_board.serial_io import configure_serial


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
    
    # Start API server
    try:
        await serve_api(config.api)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=e)
        raise
    finally:
        logger.info("IO Board Control Service Stopped")


if __name__ == "__main__":
    asyncio.run(main())


