#!/bin/bash
# Quick start script for IO Board Control Service (Linux/Mac)

echo "========================================"
echo "IO Board Control Service - Quick Start"
echo "========================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ from https://www.python.org/"
    exit 1
fi

echo "[1/5] Checking Python version..."
python3 --version

echo
echo "[2/5] Installing dependencies..."
pip3 install fastapi uvicorn pydantic pyserial pyserial-asyncio construct

if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install dependencies"
    exit 1
fi

echo
echo "[3/5] Installing test dependencies (optional)..."
pip3 install pytest pytest-asyncio pytest-cov

echo
echo "[4/5] Setting default configuration..."
export IO_BOARD_PORT=/dev/ttyUSB0
export IO_BOARD_BAUDRATE=38400
export IO_BOARD_API_HOST=0.0.0.0
export IO_BOARD_API_PORT=8000
export IO_BOARD_API_LOG_LEVEL=info

echo "Configuration:"
echo "  Port: $IO_BOARD_PORT"
echo "  Baudrate: $IO_BOARD_BAUDRATE"
echo "  API: $IO_BOARD_API_HOST:$IO_BOARD_API_PORT"
echo "  Log Level: $IO_BOARD_API_LOG_LEVEL"

echo
echo "[5/5] Configuration complete!"
echo
echo "========================================"
echo "Next Steps:"
echo "========================================"
echo
echo "1. Adjust configuration (optional):"
echo "   export IO_BOARD_PORT=/dev/ttyUSB0"
echo
echo "2. Run tests:"
echo "   python3 test_protocol_standalone.py"
echo "   python3 test_config_standalone.py"
echo
echo "3. Start the service:"
echo "   cd src/io_board"
echo "   python3 main.py"
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
