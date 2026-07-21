@echo off
REM Quick start script for IO Board Control Service (Windows)
REM 의존성은 uv(pyproject.toml + uv.lock)로 단일 관리한다.

echo ========================================
echo IO Board Control Service - Quick Start
echo ========================================
echo.

REM Check if uv is installed
uv --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv is not installed or not in PATH
    echo Install it from https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

echo [1/4] Checking uv version...
uv --version

echo.
echo [2/4] Installing dependencies (uv sync)...
uv sync

if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [3/4] Setting default configuration...
set IO_BOARD__SERIAL__PORT=COM3
set IO_BOARD__SERIAL__BAUDRATE=38400
set IO_BOARD__API__HOST=0.0.0.0
set IO_BOARD__API__PORT=8000
set IO_BOARD__API__LOG_LEVEL=info

echo Configuration:
echo   Port: %IO_BOARD__SERIAL__PORT%
echo   Baudrate: %IO_BOARD__SERIAL__BAUDRATE%
echo   API: %IO_BOARD__API__HOST%:%IO_BOARD__API__PORT%
echo   Log Level: %IO_BOARD__API__LOG_LEVEL%

echo.
echo [4/4] Configuration complete!
echo.
echo ========================================
echo Next Steps:
echo ========================================
echo.
echo 1. Adjust configuration (optional):
echo    set IO_BOARD__SERIAL__PORT=YOUR_COM_PORT
echo.
echo 2. Run tests:
echo    uv run pytest tests/
echo.
echo 3. Start the service:
echo    uv run src/main.py
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
