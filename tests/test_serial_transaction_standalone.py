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


def test_unrelated_response_is_discarded_without_resend(monkeypatch):
    reader, _ = _setup(monkeypatch)
    sends = 0
    reads = 0

    async def send_once(_reader, _writer, _message):
        nonlocal sends
        sends += 1
        return _frame("RQ", "ER")

    async def read_expected(actual_reader):
        nonlocal reads
        assert actual_reader is reader
        reads += 1
        return _frame("RQ", "ID")

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", send_once)
    monkeypatch.setattr(serial_io, "_read_response_with_timeout", read_expected)

    async def run():
        return await serial_io.fetch(
            b"\x02RQID\x03\x00",
            expected_command="RQ",
            expected_subcommand="ID",
        )

    response = asyncio.run(run())
    assert serial_io._response_codes(response) == ("RQ", "ID")
    assert sends == 1
    assert reads == 1


def test_mismatch_log_contains_lossless_frame_and_wire_timing(monkeypatch, caplog):
    reader, _ = _setup(monkeypatch)
    wrong = _frame("RQ", "ID", b"CLOSEDLOCKED")
    expected = _frame("RQ", "IW", b"+00000" * 10)

    async def send_once(_reader, _writer, _message):
        return wrong

    async def read_expected(actual_reader):
        assert actual_reader is reader
        return expected

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", send_once)
    monkeypatch.setattr(serial_io, "_read_response_with_timeout", read_expected)

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


def test_transaction_keeps_serial_ownership_while_waiting_for_match(monkeypatch):
    _setup(monkeypatch)
    allow_expected = asyncio.Event()
    sent: list[bytes] = []

    async def send(_reader, _writer, message):
        sent.append(message[1:5])
        if message[1:5] == b"RQID":
            return _frame("RQ", "ER")
        return _frame("RQ", "IW")

    async def read_expected(_reader):
        await allow_expected.wait()
        return _frame("RQ", "ID")

    monkeypatch.setattr(serial_io, "_fetch_with_timeout", send)
    monkeypatch.setattr(serial_io, "_read_response_with_timeout", read_expected)

    async def run():
        first = asyncio.create_task(
            serial_io.fetch(
                b"\x02RQID\x03\x00",
                expected_command="RQ",
                expected_subcommand="ID",
            )
        )
        await asyncio.sleep(0)
        second = asyncio.create_task(
            serial_io.fetch(
                b"\x02RQIW\x03\x00",
                expected_command="RQ",
                expected_subcommand="IW",
            )
        )
        await asyncio.sleep(0)
        assert sent == [b"RQID"]
        allow_expected.set()
        await asyncio.gather(first, second)

    asyncio.run(run())
    assert sent == [b"RQID", b"RQIW"]


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
