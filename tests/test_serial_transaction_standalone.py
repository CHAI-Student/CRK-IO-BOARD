"""Serial transaction ownership and wire retry regression tests."""

import asyncio
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


def _frame(command: str, subcommand: str) -> bytes:
    # fetch()의 transaction matching은 header만 가볍게 확인한다. 정식 frame
    # checksum 검증은 commands.parse_response()의 별도 책임이다.
    return b"\x02" + command.encode() + subcommand.encode() + b"\x03\x00"


def _setup(monkeypatch, *, max_retries: int = 3, retry_delay: float = 0.01):
    serial_io.configure_serial(
        SerialModel(max_retries=max_retries, initial_retry_delay=retry_delay)
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
