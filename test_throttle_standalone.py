"""
Unit tests for the loadcell request throttle.

INSTALLATION:
1. Create 'tests' directory in project root
2. Move this file to tests/test_throttle.py
3. Install: pip install pytest
4. Run: pytest tests/test_throttle.py

The firmware reports garbage signs when RQIW requests are spaced closer
than ~0.7s (docs/FIRMWARE_SIGN_GLITCH_REQUEST.md), so all consumers share
one throttled gate; faster calls get the cached frame.
"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import services.io_board.commands as commands
from core.config import SanitizeModel
from services.io_board.sanitizer import configure_sanitizer


@asynccontextmanager
async def fake_session(name):
    yield


def make_fake_send(counter):
    async def fake_send(command, subcommand, data):
        counter["n"] += 1
        frame = [f"+{counter['n']:05d}"] * 10
        return SimpleNamespace(DATA=SimpleNamespace(LOADCELLS=frame))
    return fake_send


def setup_function(_):
    configure_sanitizer(SanitizeModel(enabled=False))


def test_fast_calls_served_from_cache(monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(commands, "_session", fake_session)
    monkeypatch.setattr(commands, "_send_command", make_fake_send(counter))
    commands.configure_loadcell_throttle(10.0)

    async def run():
        first = await commands.get_loadcells()
        second = await commands.get_loadcells()
        return first, second

    first, second = asyncio.run(run())
    assert counter["n"] == 1          # 시리얼 요청은 1회뿐
    assert first == second            # 두 번째는 캐시


def test_gap_elapsed_triggers_fresh_request(monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(commands, "_session", fake_session)
    monkeypatch.setattr(commands, "_send_command", make_fake_send(counter))
    commands.configure_loadcell_throttle(0.05)

    async def run():
        first = await commands.get_loadcells()
        await asyncio.sleep(0.06)
        second = await commands.get_loadcells()
        return first, second

    first, second = asyncio.run(run())
    assert counter["n"] == 2
    assert first != second


def test_throttle_disabled_always_fetches(monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(commands, "_session", fake_session)
    monkeypatch.setattr(commands, "_send_command", make_fake_send(counter))
    commands.configure_loadcell_throttle(0.0)

    async def run():
        await commands.get_loadcells()
        await commands.get_loadcells()

    asyncio.run(run())
    assert counter["n"] == 2


def test_concurrent_calls_single_serial_request(monkeypatch):
    # 동시 호출이 게이트에서 직렬화되어 시리얼 요청 간격을 깨지 않는다
    counter = {"n": 0}
    monkeypatch.setattr(commands, "_session", fake_session)
    monkeypatch.setattr(commands, "_send_command", make_fake_send(counter))
    commands.configure_loadcell_throttle(10.0)

    async def run():
        return await asyncio.gather(*[commands.get_loadcells() for _ in range(5)])

    results = asyncio.run(run())
    assert counter["n"] == 1
    assert all(r == results[0] for r in results)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
