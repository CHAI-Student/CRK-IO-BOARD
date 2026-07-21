#!/bin/bash
# Quick start script for IO Board Control Service (Linux/Mac)
# 의존성은 uv(pyproject.toml + uv.lock)로 단일 관리한다.

echo "========================================"
echo "IO Board Control Service - Quick Start"
echo "========================================"
echo

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "[ERROR] uv is not installed or not in PATH"
    echo "Install it from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

echo "[1/4] Checking uv version..."
uv --version

echo
echo "[2/4] Installing dependencies (uv sync)..."
uv sync

if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install dependencies"
    exit 1
fi

echo
echo "[3/4] Setting default configuration..."
export IO_BOARD__SERIAL__PORT=/dev/ttyUSB0
export IO_BOARD__SERIAL__BAUDRATE=38400
export IO_BOARD__API__HOST=0.0.0.0
export IO_BOARD__API__PORT=8000
export IO_BOARD__API__LOG_LEVEL=info

echo "Configuration:"
echo "  Port: $IO_BOARD__SERIAL__PORT"
echo "  Baudrate: $IO_BOARD__SERIAL__BAUDRATE"
echo "  API: $IO_BOARD__API__HOST:$IO_BOARD__API__PORT"
echo "  Log Level: $IO_BOARD__API__LOG_LEVEL"

echo
echo "[4/4] Configuration complete!"
echo
echo "========================================"
echo "Next Steps:"
echo "========================================"
echo
echo "1. Adjust configuration (optional):"
echo "   export IO_BOARD__SERIAL__PORT=/dev/ttyUSB0"
echo
echo "2. Run tests:"
echo "   uv run pytest tests/"
echo
echo "3. Start the service:"
echo "   uv run src/main.py"
echo
echo "4. Access API documentation:"
echo "   Open browser: http://localhost:8000/docs"
echo
echo "5. Test the API:"
echo "   curl -X POST http://localhost:8000/init"
echo "   curl http://localhost:8000/loadcells"
echo
echo "========================================"
echo
