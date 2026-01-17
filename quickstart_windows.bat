@echo off
REM Quick start script for IO Board Control Service (Windows)

echo ========================================
echo IO Board Control Service - Quick Start
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/5] Checking Python version...
python --version

echo.
echo [2/5] Installing dependencies...
pip install fastapi uvicorn pydantic pyserial pyserial-asyncio construct

if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [3/5] Installing test dependencies (optional)...
pip install pytest pytest-asyncio pytest-cov

echo.
echo [4/5] Setting default configuration...
set IO_BOARD_PORT=COM3
set IO_BOARD_BAUDRATE=38400
set IO_BOARD_API_HOST=0.0.0.0
set IO_BOARD_API_PORT=8000
set IO_BOARD_API_LOG_LEVEL=info

echo Configuration:
echo   Port: %IO_BOARD_PORT%
echo   Baudrate: %IO_BOARD_BAUDRATE%
echo   API: %IO_BOARD_API_HOST%:%IO_BOARD_API_PORT%
echo   Log Level: %IO_BOARD_API_LOG_LEVEL%

echo.
echo [5/5] Configuration complete!
echo.
echo ========================================
echo Next Steps:
echo ========================================
echo.
echo 1. Adjust configuration (optional):
echo    set IO_BOARD_PORT=YOUR_COM_PORT
echo.
echo 2. Run tests:
echo    python test_protocol_standalone.py
echo    python test_config_standalone.py
echo.
echo 3. Start the service:
echo    cd src\io_board
echo    python main.py
echo.
echo 4. Access API documentation:
echo    Open browser: http://localhost:8000/docs
echo.
echo 5. Test the API:
echo    curl -X POST http://localhost:8000/init
echo    curl http://localhost:8000/loadcells
echo.
echo ========================================
echo.

pause
