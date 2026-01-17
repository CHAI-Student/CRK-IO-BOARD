# IO Board Refactoring - Verification Checklist

Use this checklist to verify that the refactored IO Board module is working correctly.

## ✅ Pre-Installation Verification

- [ ] Python 3.8+ installed
  ```bash
  python --version
  # or
  python3 --version
  ```

- [ ] Pip is working
  ```bash
  pip --version
  # or
  pip3 --version
  ```

## ✅ File Structure Verification

Check that all files are present:

### Core Module Files
- [ ] `src/io_board/__init__.py`
- [ ] `src/io_board/config.py`
- [ ] `src/io_board/exceptions.py`
- [ ] `src/io_board/types.py`
- [ ] `src/io_board/logging_config.py`
- [ ] `src/io_board/protocol.py`
- [ ] `src/io_board/serial_io.py`
- [ ] `src/io_board/commands.py`
- [ ] `src/io_board/api.py`
- [ ] `src/io_board/main.py`

### Test Files
- [ ] `test_protocol_standalone.py`
- [ ] `test_config_standalone.py`

### Documentation Files
- [ ] `README_IO_BOARD.md`
- [ ] `CHANGELOG_IO_BOARD.md`
- [ ] `TESTING.md`
- [ ] `REFACTORING_SUMMARY.md`
- [ ] `INDEX.md`
- [ ] This checklist file

### Utility Files
- [ ] `quickstart_windows.bat`
- [ ] `quickstart_linux.sh`
- [ ] `requirements.txt` (updated)

## ✅ Installation Verification

- [ ] Dependencies installed
  ```bash
  pip install fastapi uvicorn pydantic pyserial pyserial-asyncio construct
  ```

- [ ] Test dependencies installed (optional)
  ```bash
  pip install pytest pytest-asyncio pytest-cov
  ```

- [ ] No import errors
  ```bash
  cd src
  python -c "import io_board; print('✓ IO Board module imports successfully')"
  ```

## ✅ Configuration Verification

- [ ] Can load default configuration
  ```bash
  python -c "from io_board.config import load_config; cfg = load_config(); print('✓ Configuration loads:', cfg.serial.port)"
  ```

- [ ] Environment variables work
  ```bash
  # Windows
  set IO_BOARD_PORT=COM99
  python -c "from io_board.config import load_config; cfg = load_config(); assert cfg.serial.port == 'COM99', 'Config failed'; print('✓ Env vars work')"
  
  # Linux/Mac
  export IO_BOARD_PORT=/dev/test
  python -c "from io_board.config import load_config; cfg = load_config(); assert cfg.serial.port == '/dev/test', 'Config failed'; print('✓ Env vars work')"
  ```

- [ ] Configuration validation works
  ```bash
  python -c "from io_board.config import SerialConfig; import sys; \
  try: \
      SerialConfig('COM3', -1, 0.5, 2.0, 0.5, 3, 0.1, 2.0); \
      print('✗ Validation failed - should reject negative baudrate'); \
      sys.exit(1); \
  except ValueError: \
      print('✓ Configuration validation works')"
  ```

## ✅ Exception Hierarchy Verification

- [ ] Exception hierarchy works
  ```bash
  python -c "from io_board.exceptions import *; \
  e = SerialCommunicationError('test', ErrorCode.SERIAL_TIMEOUT); \
  assert isinstance(e, IOBoardError); \
  assert e.error_code == ErrorCode.SERIAL_TIMEOUT; \
  print('✓ Exception hierarchy works')"
  ```

- [ ] Error codes defined
  ```bash
  python -c "from io_board.exceptions import ErrorCode; \
  assert len([e for e in ErrorCode]) > 20; \
  print('✓ Error codes defined:', len([e for e in ErrorCode]), 'codes')"
  ```

## ✅ Type System Verification

- [ ] Enums defined
  ```bash
  python -c "from io_board.types import CommandType, DoorState; \
  assert CommandType.MANAGEMENT_CONTROL == 'MC'; \
  assert DoorState.OPEN == 'OPEN'; \
  print('✓ Enums defined correctly')"
  ```

- [ ] Pydantic models work
  ```bash
  python -c "from io_board.types import DeadboltRequest, DoorState; \
  req = DeadboltRequest(state=DoorState.OPEN); \
  assert req.state == DoorState.OPEN; \
  print('✓ Pydantic models work')"
  ```

## ✅ Logging System Verification

- [ ] Logging setup works
  ```bash
  python -c "from io_board.logging_config import setup_logging, get_logger; \
  setup_logging('INFO'); \
  logger = get_logger('test'); \
  logger.info('Test message'); \
  print('✓ Logging system works')"
  ```

- [ ] Correlation IDs work
  ```bash
  python -c "from io_board.logging_config import set_correlation_id, get_correlation_id; \
  cid = set_correlation_id(); \
  assert get_correlation_id() == cid; \
  print('✓ Correlation IDs work')"
  ```

## ✅ Protocol Verification

- [ ] Protocol tests pass
  ```bash
  python test_protocol_standalone.py -v
  # Should show all tests passing
  ```

- [ ] Checksum calculation works
  ```bash
  python -c "from io_board.protocol import calculate_checksum; \
  assert calculate_checksum(b'ABC') == 0x40; \
  print('✓ Checksum calculation correct')"
  ```

- [ ] Request building works
  ```bash
  python -c "from io_board.protocol import build_request, STX, ETX; \
  msg = build_request('MC', 'PD', {}); \
  assert msg[0:1] == STX and msg[-2:-1] == ETX; \
  print('✓ Request building works')"
  ```

## ✅ Configuration Tests Verification

- [ ] Configuration tests pass
  ```bash
  python test_config_standalone.py -v
  # Should show all tests passing
  ```

## ✅ API Verification (Without Hardware)

- [ ] FastAPI app loads
  ```bash
  python -c "from io_board.api import app; \
  assert app.title == 'IO Board Control API'; \
  print('✓ FastAPI app loads')"
  ```

- [ ] Endpoints defined
  ```bash
  python -c "from io_board.api import app; \
  routes = [r.path for r in app.routes]; \
  assert '/init' in routes; \
  assert '/deadbolt' in routes; \
  assert '/loadcells' in routes; \
  print('✓ All endpoints defined:', len(routes), 'routes')"
  ```

## ✅ Full Integration Test (Without Hardware)

- [ ] Service starts (will fail on serial connection, which is expected)
  ```bash
  # Set test port that doesn't exist
  # Windows: set IO_BOARD_PORT=COM999
  # Linux: export IO_BOARD_PORT=/dev/null
  
  # Try to start (will fail quickly, which is expected)
  # python src/io_board/main.py
  # Should see structured logging and clear error about serial port
  ```

- [ ] API documentation accessible (if service running)
  ```bash
  # Start service, then:
  curl http://localhost:8000/docs
  # Should return HTML documentation
  ```

## ✅ Code Quality Verification

- [ ] No wildcard imports
  ```bash
  # Should find nothing
  grep -r "from .* import \*" src/io_board/*.py
  ```

- [ ] No print statements (only logging)
  ```bash
  # Should find nothing
  grep -r "^[^#]*print(" src/io_board/*.py
  ```

- [ ] All functions have docstrings
  ```bash
  # Manual check - open any file and verify functions have docstrings
  ```

- [ ] All functions have type hints
  ```bash
  # Manual check - open any file and verify function signatures have type hints
  ```

## ✅ Documentation Verification

- [ ] README is complete
  ```bash
  # Verify README_IO_BOARD.md exists and has:
  # - Installation instructions
  # - Configuration guide
  # - API examples
  # - Error handling documentation
  ```

- [ ] CHANGELOG is complete
  ```bash
  # Verify CHANGELOG_IO_BOARD.md has:
  # - Version 2.0.0 changes
  # - Breaking changes
  # - Migration guide
  ```

- [ ] Testing guide exists
  ```bash
  # Verify TESTING.md has:
  # - Test setup instructions
  # - How to run tests
  # - Test examples
  ```

## ✅ Hardware Integration Test (With Hardware)

⚠️ **Only if you have the actual IO Board hardware connected:**

- [ ] Configure correct COM port
  ```bash
  # Windows example
  set IO_BOARD_PORT=COM3
  set IO_BOARD_BAUDRATE=38400
  ```

- [ ] Start service
  ```bash
  cd src/io_board
  python main.py
  # Should start without errors
  ```

- [ ] Test endpoints
  ```bash
  # Initialize device
  curl -X POST http://localhost:8000/init
  
  # Get product info
  curl http://localhost:8000/product_info
  
  # Get loadcells
  curl http://localhost:8000/loadcells
  
  # Stream loadcells (Ctrl+C to stop)
  curl -N http://localhost:8000/stream/loadcells
  ```

- [ ] Check logs
  ```bash
  # Logs should show:
  # - Correlation IDs
  # - Request/response timing
  # - Binary payloads in hex
  # - No errors (unless hardware issue)
  ```

## 📋 Summary

Once all checkboxes are marked:

✅ **Module structure is correct**
✅ **Dependencies installed**
✅ **Configuration system works**
✅ **Exception handling works**
✅ **Type system works**
✅ **Logging works**
✅ **Protocol implementation correct**
✅ **Tests pass**
✅ **API structure correct**
✅ **Documentation complete**
✅ **Code quality verified**

## 🎉 Success!

If all verifications pass, the refactoring is complete and the module is ready for use!

## ❌ Troubleshooting

If any verification fails:

1. **Import errors**: Check that you're running from the correct directory
2. **Module not found**: Ensure `src` is in your Python path or run from correct location
3. **Test failures**: Review test output for specific failure reasons
4. **Configuration errors**: Verify environment variables are set correctly
5. **Serial errors**: Normal if hardware not connected - verify error is clear and helpful

## 📞 Need Help?

- Check [README_IO_BOARD.md](README_IO_BOARD.md) for usage
- Check [TESTING.md](TESTING.md) for test help
- Check [INDEX.md](INDEX.md) for navigation
- Check inline docstrings in code

---

**Checklist Version**: 1.0
**Last Updated**: 2026-01-17
