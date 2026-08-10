"""Read-only health and deadbolt operation serialization regressions."""

import asyncio
from types import SimpleNamespace

from api.v1.routers import machine
from services.io_board.io_types import DeadboltAction, DeadboltState, DoorState


class _ErrorState:
    def __init__(self):
        self.actions: list[DeadboltAction] = []

    async def door_error(self) -> bool:
        return True

    async def deadbolt_error(self) -> bool:
        return True

    async def set_deadbolt_action(self, action: DeadboltAction) -> None:
        self.actions.append(action)


def _request(error_state: _ErrorState, *, lock=None):
    state = SimpleNamespace(
        recording_services={"error_state_management": error_state},
        settings=SimpleNamespace(
            health=SimpleNamespace(
                loadcell_min_grams=-40000,
                loadcell_max_grams=40000,
            )
        ),
    )
    if lock is not None:
        state.deadbolt_operation_lock = lock
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_health_is_read_only_and_does_not_consume_error_history(monkeypatch):
    error_state = _ErrorState()
    calls: list[str] = []

    async def get_loadcells():
        calls.append("RQIW")
        return ["+00000"] * 10

    async def get_status():
        calls.append("RQID")
        return {"door": DoorState.CLOSED, "deadbolt": DeadboltState.LOCKED}

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("health must not mutate or inspect sticky error history")

    monkeypatch.setattr(machine.commands, "get_loadcells", get_loadcells)
    monkeypatch.setattr(machine.commands, "get_status", get_status)
    monkeypatch.setattr(machine.commands, "clear_errors", forbidden)
    monkeypatch.setattr(machine.commands, "set_deadbolt", forbidden)
    monkeypatch.setattr(machine.commands, "get_errors", forbidden)

    response = asyncio.run(machine.get_health(_request(error_state)))

    assert response == machine.HealthResponse(
        deadbolt="HEALTHY", loadcells="HEALTHY", door="HEALTHY"
    )
    assert calls == ["RQIW", "RQID"]


def test_deadbolt_lock_covers_command_settle_and_status_verification(monkeypatch):
    error_state = _ErrorState()
    events: list[str] = []
    current_state = DeadboltState.LOCKED

    async def set_deadbolt(action: DeadboltAction):
        nonlocal current_state
        events.append(f"MCDC:{action.value}")
        current_state = (
            DeadboltState.UNLOCK
            if action == DeadboltAction.OPEN
            else DeadboltState.LOCKED
        )
        return current_state

    async def get_status():
        events.append(f"RQID:{current_state.value}")
        return {"door": DoorState.CLOSED, "deadbolt": current_state}

    monkeypatch.setattr(machine.commands, "set_deadbolt", set_deadbolt)
    monkeypatch.setattr(machine.commands, "get_status", get_status)
    monkeypatch.setattr(machine, "DEADBOLT_SETTLE_SECONDS", 0)

    async def run():
        request = _request(error_state, lock=asyncio.Lock())
        first = asyncio.create_task(
            machine.set_deadbolt(
                request, machine.DeadboltRequest(action=DeadboltAction.OPEN)
            )
        )
        await asyncio.sleep(0)
        second = asyncio.create_task(
            machine.set_deadbolt(
                request, machine.DeadboltRequest(action=DeadboltAction.CLOSE)
            )
        )
        return await asyncio.gather(first, second)

    responses = asyncio.run(run())

    assert [response.state for response in responses] == [
        DeadboltState.UNLOCK,
        DeadboltState.LOCKED,
    ]
    assert error_state.actions == [DeadboltAction.OPEN, DeadboltAction.CLOSE]
    assert events == [
        "MCDC:OPEN",
        "RQID:UNLOCK",
        "MCDC:CLOSE",
        "RQID:LOCKED",
    ]
