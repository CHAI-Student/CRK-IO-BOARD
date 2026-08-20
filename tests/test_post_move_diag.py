"""Unit tests for the read-only post-move diagnostic analyzer."""

from pathlib import Path
import sys


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from post_move_diag import Thresholds, analyze, parse_loadcell  # noqa: E402


def frame(value: int = 0) -> list[str]:
    sign = "+" if value >= 0 else "-"
    return [f"{sign}{abs(value):05d}"] * 10


def capture(
    frames: list[list[str]],
    *,
    interval: float = 0.85,
    health: dict | None = None,
    product_id: str = "ABC12345678",
    software: str = "01",
    errors: list[str] | None = None,
    statuses: list[tuple[str, str]] | None = None,
    request_records: list[dict] | None = None,
) -> dict:
    statuses = statuses or [("CLOSED", "LOCKED")]
    requests = request_records or [
        {"path": "/loadcells", "ok": True, "latency_ms": 10.0}
        for _ in frames
    ]
    return {
        "settings": {"interval_seconds": interval},
        "product_info": {"product_id": product_id, "sw_version": software},
        "health": health
        or {"loadcells": "HEALTHY", "door": "HEALTHY", "deadbolt": "HEALTHY"},
        "device_errors": {
            "errors": [{"code": code} for code in (errors or ["0000"] * 4)]
        },
        "loadcell_samples": [
            {"timestamp": f"t{index}", "loadcells": values, "latency_ms": 10.0}
            for index, values in enumerate(frames)
        ],
        "status_samples": [
            {"timestamp": f"s{index}", "door": door, "deadbolt": deadbolt}
            for index, (door, deadbolt) in enumerate(statuses)
        ],
        "requests": requests,
    }


def thresholds(**overrides) -> Thresholds:
    values = {"min_samples": 3}
    values.update(overrides)
    return Thresholds(**values)


def codes(report: dict) -> set[str]:
    return {item["code"] for item in report["issues"]}


def test_parse_loadcell_formats_and_markers():
    assert parse_loadcell("+00125") == (125.0, None)
    assert parse_loadcell("-123.4") == (-123.4, None)
    assert parse_loadcell("EEEEEE") == (None, "EEEEEE")
    assert parse_loadcell("125") == (None, "malformed")
    assert parse_loadcell(None) == (None, "malformed")


def test_stable_capture_passes():
    report = analyze(capture([frame(), frame(), frame()]), thresholds=thresholds())

    assert report["overall"] == "PASS"
    assert report["issues"] == []
    assert all(channel["stddev"] == 0.0 for channel in report["channels"])


def test_error_markers_fail_channel():
    frames = [frame(), frame(), frame()]
    for values in frames:
        values[4] = "EEEEEE"

    report = analyze(capture(frames), thresholds=thresholds())

    assert report["overall"] == "FAIL"
    assert "LOADCELL_ERROR_MARKER" in codes(report)
    assert any(
        item.get("channel") == 4 and item["severity"] == "FAIL"
        for item in report["issues"]
    )


def test_empty_offset_and_noise_are_detected():
    frames = [frame(), frame(), frame()]
    for values, reading in zip(frames, (250, 300, 350)):
        values[2] = f"+{reading:05d}"

    report = analyze(capture(frames), thresholds=thresholds(), empty=True)

    assert report["overall"] == "FAIL"
    assert {"EMPTY_ZERO_OFFSET", "LOADCELL_NOISY", "LOADCELL_RANGE_UNSTABLE"} <= codes(report)


def test_baseline_detects_board_and_channel_shift():
    baseline_capture = capture([frame(), frame(), frame()])
    baseline_capture["analysis"] = analyze(
        baseline_capture, thresholds=thresholds()
    )
    moved_frames = [frame(), frame(), frame()]
    for values in moved_frames:
        values[0] = "+00150"

    report = analyze(
        capture(moved_frames, product_id="ZZZ12345678"),
        thresholds=thresholds(),
        baseline=baseline_capture,
    )

    assert report["overall"] == "FAIL"
    assert {"PRODUCT_ID_CHANGED", "BASELINE_MEAN_SHIFT"} <= codes(report)


def test_health_and_expected_status_mismatch_fail():
    report = analyze(
        capture(
            [frame(), frame(), frame()],
            health={"loadcells": "HEALTHY", "door": "UNHEALTHY", "deadbolt": "HEALTHY"},
            statuses=[("OPENED", "UNLOCK")] * 3,
        ),
        thresholds=thresholds(),
        expected_door="CLOSED",
        expected_deadbolt="LOCKED",
    )

    assert report["overall"] == "FAIL"
    assert {
        "HEALTH_UNHEALTHY",
        "DOOR_EXPECTED_STATE_MISMATCH",
        "DEADBOLT_EXPECTED_STATE_MISMATCH",
    } <= codes(report)


def test_short_interval_and_error_history_warn():
    report = analyze(
        capture(
            [frame(), frame(), frame()],
            interval=0.05,
            errors=["LC01", "0000", "0000", "0000"],
        ),
        thresholds=thresholds(),
    )

    assert report["overall"] == "WARN"
    assert {"CAPTURE_INTERVAL_BELOW_THROTTLE", "DEVICE_ERROR_HISTORY_PRESENT"} <= codes(report)


def test_request_failures_and_latency_are_reported():
    requests = [
        {"path": "/loadcells", "ok": True, "latency_ms": 3000.0},
        {"path": "/status", "ok": False, "latency_ms": 3000.0},
        {"path": "/loadcells", "ok": True, "latency_ms": 3000.0},
    ]
    report = analyze(
        capture([frame(), frame(), frame()], request_records=requests),
        thresholds=thresholds(),
    )

    assert report["overall"] == "FAIL"
    assert {"API_REQUEST_FAILURES", "API_LATENCY_HIGH"} <= codes(report)
