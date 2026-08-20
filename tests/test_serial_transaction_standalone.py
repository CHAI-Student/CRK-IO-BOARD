"""Serial transaction ownership and wire retry regression tests."""

import asyncio
import logging
from types import SimpleNamespace

from core.config import SerialModel
from services.io_board import commands
from services.io_board import serial_io
from services.io_board.io_types import CommandType, RequestSubcommand


class _Writer:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


def _frame(command: str, subcommand: str, data: bytes = b"") -> bytes:
    # fetch()의 transaction matching은 header만 가볍게 확인한다. 정식 frame
    # checksum 검증은 commands.parse_response()의 별도 책임이다.
    payload = command.encode() + subcommand.encode() + data + b"\x03"
    checksum = serial_io._xor_checksum(payload)
    return b"\x02" + payload + bytes([checksum])


def _setup(
    monkeypatch,
    *,
    max_retries: int = 3,
    retry_delay: float = 0.01,
    inter_command_gap: float = 0.0,
):
    serial_io.configure_serial(
        SerialModel(
            max_retries=max_retries,
            initial_retry_delay=retry_delay,
            inter_command_gap=inter_command_gap,
        )
    )
    reader = object()
    writer = _Writer()

    async def connection():
        return reader, writer

    async def no_drain(_reader):
        return None

    monkeypatch.setattr(serial_io, "get_serial_connection", connection)
    monkeypatch.setattr(serial_io, "_drain_stale_input", no_drain)
    return reader, writer


def test_unrelated_response_retries_same_request(monkeypatch):
    _setup(monkeypatch)
    responses = [_frame("RQ", "ER"), _frame("RQ", "ID")]
    sent: list[bytes] = []

    async def send(_reader, _writer, message):
        sent.append(message[1:5])
        return responses.pop(0)

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", send)

    async def run():
        return await serial_io.fetch(
            b"\x02RQID\x03\x00",
            expected_command="RQ",
            expected_subcommand="ID",
        )

    response = asyncio.run(run())
    assert serial_io._response_codes(response) == ("RQ", "ID")
    assert sent == [b"RQID", b"RQID"]


def test_mismatch_log_contains_lossless_frame_and_wire_timing(monkeypatch, caplog):
    _setup(monkeypatch)
    wrong = _frame("RQ", "ID", b"CLOSEDLOCKED")
    expected = _frame("RQ", "IW", b"+00000" * 10)
    responses = [wrong, expected]

    async def send(_reader, _writer, _message):
        return responses.pop(0)

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", send)

    caplog.set_level(logging.WARNING, logger=serial_io.logger.name)

    async def run():
        return await serial_io.fetch(
            _frame("RQ", "IW"),
            expected_command="RQ",
            expected_subcommand="IW",
        )

    assert asyncio.run(run()) == expected
    messages = [record.getMessage() for record in caplog.records]
    mismatch = next(msg for msg in messages if msg.startswith("Unexpected response"))
    recovered = next(msg for msg in messages if msg.startswith("Serial transaction recovered"))

    assert "txn=1 attempt=1/3" in mismatch
    assert "expected=RQ/IW got=RQ/ID" in mismatch
    assert "rx_after_tx_ms=" in mismatch
    assert "previous_tx=none tx_gap_ms=none" in mismatch
    assert "rx_len=19" in mismatch
    assert "rx_shape=known-response-size" in mismatch
    assert "rx_checksum=valid" in mismatch
    assert f"rx_hex={wrong.hex().upper()}" in mismatch
    assert "retrying same request" in mismatch
    assert "attempt=2/3" in recovered
    assert "discarded_total=1" in recovered
    assert "rx_len=67" in recovered


def test_frame_diagnostics_distinguishes_echo_and_corruption():
    echo = _frame("RQ", "ID")
    echo_diagnostics = serial_io._frame_diagnostics(echo)
    assert "rx_len=7" in echo_diagnostics
    assert "rx_shape=request-sized-or-empty-response" in echo_diagnostics
    assert "rx_checksum=valid" in echo_diagnostics

    corrupted = echo[:-1] + bytes([echo[-1] ^ 0xFF])
    corrupted_diagnostics = serial_io._frame_diagnostics(corrupted)
    assert "rx_checksum=invalid" in corrupted_diagnostics
    assert f"rx_hex={corrupted.hex().upper()}" in corrupted_diagnostics


def test_transaction_keeps_serial_ownership_across_mismatch_retry(monkeypatch):
    _setup(monkeypatch)
    retry_started = asyncio.Event()
    allow_retry_response = asyncio.Event()
    sent: list[bytes] = []
    rqid_attempts = 0

    async def send(_reader, _writer, message):
        nonlocal rqid_attempts
        sent.append(message[1:5])
        if message[1:5] == b"RQID":
            rqid_attempts += 1
            if rqid_attempts == 1:
                return _frame("RQ", "ER")
            retry_started.set()
            await allow_retry_response.wait()
            return _frame("RQ", "ID")
        return _frame("RQ", "IW")

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", send)

    async def run():
        first = asyncio.create_task(
            serial_io.fetch(
                b"\x02RQID\x03\x00",
                expected_command="RQ",
                expected_subcommand="ID",
            )
        )
        await retry_started.wait()
        assert sent == [b"RQID", b"RQID"]
        second = asyncio.create_task(
            serial_io.fetch(
                b"\x02RQIW\x03\x00",
                expected_command="RQ",
                expected_subcommand="IW",
            )
        )
        await asyncio.sleep(0)
        assert sent == [b"RQID", b"RQID"]
        allow_retry_response.set()
        await asyncio.gather(first, second)

    asyncio.run(run())
    assert sent == [b"RQID", b"RQID", b"RQIW"]


def test_fetch_without_expected_codes_returns_response(monkeypatch):
    _setup(monkeypatch)
    expected = _frame("RQ", "ID")

    async def send(_reader, _writer, _message):
        return expected

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", send)

    response = asyncio.run(serial_io.fetch(_frame("RQ", "ID")))
    assert response == expected


def test_wire_min_gap_applies_to_timeout_retry(monkeypatch):
    _setup(monkeypatch, max_retries=2, retry_delay=0.01)
    send_times: list[float] = []

    async def timeout_then_success(_reader, _writer, _message):
        send_times.append(asyncio.get_running_loop().time())
        if len(send_times) == 1:
            raise asyncio.TimeoutError
        return _frame("RQ", "IW")

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", timeout_then_success)

    async def run():
        await serial_io.fetch(
            b"\x02RQIW\x03\x00",
            expected_command="RQ",
            expected_subcommand="IW",
            min_send_interval=0.05,
        )

    asyncio.run(run())
    assert len(send_times) == 2
    assert send_times[1] - send_times[0] >= 0.045


def test_inter_command_gap_is_measured_from_complete_rx(monkeypatch):
    _setup(monkeypatch, inter_command_gap=0.05)
    send_times: list[float] = []
    rx_complete_times: list[float] = []

    async def respond(_reader, _writer, message):
        send_times.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.005)
        rx_complete_times.append(asyncio.get_running_loop().time())
        command, subcommand = serial_io._response_codes(message)
        return _frame(command, subcommand)

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", respond)

    async def run():
        await serial_io.fetch(
            _frame("RQ", "ID"),
            expected_command="RQ",
            expected_subcommand="ID",
        )
        await serial_io.fetch(
            _frame("RQ", "IW"),
            expected_command="RQ",
            expected_subcommand="IW",
        )

    asyncio.run(run())
    assert len(send_times) == 2
    assert send_times[1] - rx_complete_times[0] >= 0.045


def test_loadcell_command_passes_configured_gap_to_wire(monkeypatch):
    commands.configure_loadcell_throttle(0.75)
    captured = {}

    monkeypatch.setattr(commands, "build_request", lambda *_args: b"request")

    async def fake_fetch(message, **kwargs):
        captured["message"] = message
        captured.update(kwargs)
        return b"response"

    monkeypatch.setattr(commands, "fetch", fake_fetch)
    monkeypatch.setattr(
        commands,
        "parse_response",
        lambda _message: SimpleNamespace(COMMAND="RQ", SUBCOMMAND="IW"),
    )

    async def run():
        await commands._send_command(
            CommandType.REQUEST,
            RequestSubcommand.LOADCELL_WEIGHTS,
            {},
        )

    asyncio.run(run())
    assert captured == {
        "message": b"request",
        "expected_command": "RQ",
        "expected_subcommand": "IW",
        "min_send_interval": 0.75,
    }
