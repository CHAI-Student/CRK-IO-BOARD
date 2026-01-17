# IO Board Testing Guide

## Setup

### 1. Create Tests Directory
```bash
mkdir tests
```

### 2. Install Test Dependencies
```bash
pip install pytest pytest-asyncio pytest-cov
```

### 3. Install IO Board Dependencies
```bash
pip install fastapi uvicorn pydantic pyserial pyserial-asyncio construct
```

## Test Files

Create the following test files in the `tests/` directory:

### `tests/__init__.py`
```python
"""IO Board unit tests package."""
```

### `tests/test_protocol.py`
See the test file content in the repository.

### `tests/test_commands.py`  
Tests for high-level command execution (requires mocking serial communication).

### `tests/test_config.py`
Tests for configuration loading and validation.

## Running Tests

### Run All Tests
```bash
pytest tests/
```

### Run with Coverage
```bash
pytest --cov=src.io_board --cov-report=html tests/
```

### Run Specific Test File
```bash
pytest tests/test_protocol.py
```

### Run Specific Test Class
```bash
pytest tests/test_protocol.py::TestChecksumCalculation
```

### Run with Verbose Output
```bash
pytest -v tests/
```

## Test Structure

- `test_protocol.py` - Tests for protocol encoding/decoding
  - TestChecksumCalculation - Checksum algorithm tests
  - TestRequestBuilding - Request message building tests
  - TestResponseParsing - Response message parsing tests
  - TestRoundTrip - End-to-end protocol tests

- `test_commands.py` - Tests for high-level commands (mock serial)
  - TestInitialize
  - TestDoorControl
  - TestCalibrate
  - TestManufacturingNumber
  - TestDataRetrieval

- `test_config.py` - Tests for configuration management
  - TestSerialConfig
  - TestAPIConfig
  - TestConfigLoading

## Environment Variables for Testing

Set these before running tests that need specific configuration:

```bash
set IO_BOARD_PORT=COM_TEST
set IO_BOARD_BAUDRATE=38400
set IO_BOARD_API_HOST=127.0.0.1
set IO_BOARD_API_PORT=8001
```

## Continuous Integration

Add to your CI pipeline:

```yaml
- name: Install dependencies
  run: |
    pip install pytest pytest-asyncio pytest-cov
    pip install -r requirements.txt

- name: Run tests
  run: pytest --cov=src.io_board tests/

- name: Generate coverage report
  run: pytest --cov=src.io_board --cov-report=xml tests/
```
