## Usage Guide and Testing

### Quickstart
1) Install dependencies: `pip install -r requirements.txt`
2) Export env if needed (Windows example):
   - `set IO_BOARD_PORT=COM3`
   - `set IO_BOARD_API_PORT=8000`
3) Run service: `python src/main.py`
4) Call endpoints with curl/httpie or open browser for REST.

### Common REST Calls
- Initialize board: `curl -X POST http://localhost:8000/init`
- Calibrate (shelves empty): `curl -X POST http://localhost:8000/calibrate`
- Set manufacturing number: `curl -X POST http://localhost:8000/manufacturing_number -H "Content-Type: application/json" -d "{\"manufacturing_number\":\"P1234567890\"}"`
- Control deadbolt: `curl -X POST http://localhost:8000/deadbolt -H "Content-Type: application/json" -d "{\"state\":\"OPEN\"}"`
- Get loadcells: `curl http://localhost:8000/loadcells`
- Get door/deadbolt status: `curl http://localhost:8000/status`
- Clear errors: `curl -X DELETE http://localhost:8000/errors`
- Reboot: `curl -X POST http://localhost:8000/reboot`

### Streaming
- Legacy (deprecated): `curl -N http://localhost:8000/stream/loadcells`
  - Emits `event: update` with `{loadcells:[...]} ` at `IO_BOARD_STREAM_INTERVAL` seconds.
- Unified SSE examples:
  - Loadcells only: `curl -N "http://localhost:8000/sse?streams=loadcells&loadcell_interval=0.5"`
  - Loadcells + doors: `curl -N "http://localhost:8000/sse?streams=loadcells,doors&loadcell_interval=0.2&door_interval=1.0"`
  - With filtering: `curl -N "http://localhost:8000/sse?streams=loadcells&filter_method=exponential&filter_alpha=0.3"`
  - Threshold detection: `curl -N "http://localhost:8000/sse?streams=loadcells&threshold=10.0&threshold_scope=filtered"`
  - Per-loadcell thresholds: `curl -N "http://localhost:8000/sse?streams=loadcells&threshold=1,2,3,4,5,6,7,8,9,10&threshold_scope=raw"`

Event names: `loadcell.update`, `loadcell.change`, `loadcell.uncertainty`, `door.update`, `error`.

### Data Formats and Ranges
- Loadcell strings: `+/-` + five digits; errors `EEEEEE` (no comms) or `VVVVVV` (range). Hardware spec range -40000..+40000 (grams).
- Door/deadbolt strings: 6 chars (`CLOSED`, `OPENED`, `LOCKED`, etc.).
- Manufacturing ID: 11 ASCII characters.
- Error history: 4 entries, codes such as DB01 (unlock fail), DB02 (lock fail), LC01–LC10 (loadcell comms/range), or `0000`.

### Filtering and Thresholds
- Methods: `none`, `exponential(alpha)`, `kalman(q,r)` per loadcell.
- Thresholds: single value broadcast to all 10 or comma list of 10. Scope: `raw` compares unfiltered numeric values; `filtered` uses smoothed values.
- Uncertainty: any `EEEEEE`/`VVVVVV` or parse failure triggers `loadcell.uncertainty`; IOBoardError triggers uncertainty for all indices and an `error` event.

### Testing
- Reference: [TESTING.md](TESTING.md) for setup and pytest commands.
- Key test files (can be run in-place or moved under `tests/` as documented):
  - Protocol: [test_protocol_standalone.py](test_protocol_standalone.py)
  - Config: [test_config_standalone.py](test_config_standalone.py)
  - SSE filters/detector: [test_sse_feature.py](test_sse_feature.py)
- Typical commands:
  - `pytest test_protocol_standalone.py -v`
  - `pytest test_config_standalone.py -v`
  - `python test_sse_feature.py`
- For coverage (if moved to `tests/`): `pytest --cov=src.io_board --cov-report=html tests/`
