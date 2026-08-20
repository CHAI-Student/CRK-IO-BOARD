#!/usr/bin/env python3
"""기기 이동·충격 후 IO Board 상태를 점검하는 read-only 진단 도구.

현재 서비스 설정(sanitizer, loadcell throttle)을 바꾸지 않고 외부 API에서
관측되는 상태를 검사한다. 장비를 이동하기 전 ``baseline``을 저장해 두면 이동
후 ``check``에서 채널 offset과 noise 변화를 비교할 수 있다.

사용법:
  python3 tools/post_move_diag.py baseline -o before_move.json
  python3 tools/post_move_diag.py check --baseline before_move.json
  python3 tools/post_move_diag.py check --empty --expect-door CLOSED --expect-deadbolt LOCKED

종료 코드: PASS=0, WARN=1, FAIL=2
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any
import urllib.error
import urllib.request


SCHEMA_VERSION = 1
CHANNELS = 10
ERROR_VALUES = {"EEEEEE", "VVVVVV"}
VALUE_PATTERN = re.compile(r"^[+-](?:\d{5}|\d{3}\.\d)$")
SEVERITY_RANK = {"INFO": 0, "WARN": 1, "FAIL": 2}


@dataclass(frozen=True)
class Thresholds:
    """진단 판정 기준. CLI option으로 모두 조정할 수 있다."""

    min_samples: int = 20
    marker_fail_rate: float = 0.05
    noise_std_warn: float = 5.0
    noise_std_fail: float = 15.0
    range_warn: float = 20.0
    range_fail: float = 50.0
    empty_offset_warn: float = 50.0
    empty_offset_fail: float = 200.0
    baseline_shift_warn: float = 20.0
    baseline_shift_fail: float = 100.0
    baseline_noise_ratio_warn: float = 3.0
    baseline_noise_ratio_fail: float = 5.0
    latency_warn_ms: float = 1000.0
    latency_fail_ms: float = 2500.0
    request_failure_rate_fail: float = 0.10


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)
    return ordered[max(index, 0)]


def parse_loadcell(value: Any) -> tuple[float | None, str | None]:
    """판독값을 (숫자, 오류 종류)로 변환한다."""
    if not isinstance(value, str):
        return None, "malformed"
    if value in ERROR_VALUES:
        return None, value
    if not VALUE_PATTERN.fullmatch(value):
        return None, "malformed"
    try:
        return float(value), None
    except ValueError:
        return None, "malformed"


def issue(
    severity: str,
    code: str,
    message: str,
    *,
    channel: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if channel is not None:
        result["channel"] = channel
    if details:
        result["details"] = details
    return result


def _request_json(base_url: str, path: str, timeout: float) -> tuple[Any, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{path}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "crk-post-move-diag/1"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            payload = json.loads(body)
            return payload, {
                "timestamp": utc_now(),
                "path": path,
                "ok": True,
                "status": response.status,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "correlation_id": response.headers.get("X-Correlation-ID"),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload: Any = json.loads(body)
        except json.JSONDecodeError:
            error_payload = body
        return None, {
            "timestamp": utc_now(),
            "path": path,
            "ok": False,
            "status": exc.code,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "error": error_payload,
        }
    except Exception as exc:  # noqa: BLE001 - 진단은 다음 sample을 계속 수집한다
        return None, {
            "timestamp": utc_now(),
            "path": path,
            "ok": False,
            "status": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def collect(
    base_url: str,
    duration: float,
    interval: float,
    timeout: float,
    status_every: int,
) -> dict[str, Any]:
    """API snapshot과 loadcell 시계열을 수집한다."""
    capture: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "captured_at": utc_now(),
        "base_url": base_url.rstrip("/"),
        "settings": {
            "duration_seconds": duration,
            "interval_seconds": interval,
            "timeout_seconds": timeout,
            "status_every": status_every,
            "data_stage": "post-sanitizer/post-throttle",
        },
        "product_info": None,
        "health": None,
        "device_errors": None,
        "loadcell_samples": [],
        "status_samples": [],
        "requests": [],
    }

    for key, path in (
        ("product_info", "/product-info"),
        ("health", "/health"),
        ("device_errors", "/errors"),
    ):
        payload, record = _request_json(base_url, path, timeout)
        capture[key] = payload
        capture["requests"].append(record)

    deadline = time.monotonic() + duration
    sample_index = 0
    while time.monotonic() < deadline:
        cycle_started = time.monotonic()
        payload, record = _request_json(base_url, "/loadcells", timeout)
        capture["requests"].append(record)
        if payload is not None:
            capture["loadcell_samples"].append(
                {
                    "timestamp": record["timestamp"],
                    "loadcells": payload.get("loadcells"),
                    "latency_ms": record["latency_ms"],
                    "correlation_id": record.get("correlation_id"),
                }
            )

        if sample_index % status_every == 0:
            status, status_record = _request_json(base_url, "/status", timeout)
            capture["requests"].append(status_record)
            if status is not None:
                capture["status_samples"].append(
                    {
                        "timestamp": status_record["timestamp"],
                        "door": status.get("door"),
                        "deadbolt": status.get("deadbolt"),
                        "latency_ms": status_record["latency_ms"],
                        "correlation_id": status_record.get("correlation_id"),
                    }
                )

        sample_index += 1
        if sample_index % 10 == 0:
            print(
                f"  collected {len(capture['loadcell_samples'])} loadcell samples...",
                file=sys.stderr,
            )
        remaining = interval - (time.monotonic() - cycle_started)
        if remaining > 0:
            time.sleep(remaining)

    return capture


def channel_stats(capture: dict[str, Any]) -> list[dict[str, Any]]:
    samples = capture.get("loadcell_samples", [])
    channels: list[dict[str, Any]] = []
    for channel in range(CHANNELS):
        values: list[float] = []
        markers = {"EEEEEE": 0, "VVVVVV": 0, "malformed": 0}
        for sample in samples:
            row = sample.get("loadcells")
            if not isinstance(row, list) or len(row) != CHANNELS:
                markers["malformed"] += 1
                continue
            numeric, error = parse_loadcell(row[channel])
            if error is not None:
                markers[error] += 1
            elif numeric is not None:
                values.append(numeric)

        stats: dict[str, Any] = {
            "channel": channel,
            "sample_count": len(samples),
            "valid_count": len(values),
            "error_counts": markers,
            "error_rate": (
                round(sum(markers.values()) / len(samples), 6) if samples else 1.0
            ),
            "unique_values": len(set(values)),
        }
        if values:
            stats.update(
                {
                    "mean": round(statistics.fmean(values), 3),
                    "stddev": round(statistics.pstdev(values), 3),
                    "min": min(values),
                    "max": max(values),
                    "range": max(values) - min(values),
                }
            )
        else:
            stats.update(
                {"mean": None, "stddev": None, "min": None, "max": None, "range": None}
            )
        channels.append(stats)
    return channels


def _baseline_channels(baseline: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    if baseline is None:
        return None
    analysis = baseline.get("analysis")
    if isinstance(analysis, dict) and isinstance(analysis.get("channels"), list):
        return analysis["channels"]
    if isinstance(baseline.get("loadcell_samples"), list):
        return channel_stats(baseline)
    return None


def analyze(
    capture: dict[str, Any],
    *,
    thresholds: Thresholds,
    baseline: dict[str, Any] | None = None,
    empty: bool = False,
    expected_door: str | None = None,
    expected_deadbolt: str | None = None,
) -> dict[str, Any]:
    """수집 결과를 판정한다. 네트워크 없이 단위 테스트 가능한 pure analysis."""
    issues: list[dict[str, Any]] = []
    channels = channel_stats(capture)
    base_channels = _baseline_channels(baseline)
    samples = capture.get("loadcell_samples", [])

    if baseline is not None and base_channels is None:
        issues.append(
            issue(
                "WARN",
                "BASELINE_LOADCELLS_UNAVAILABLE",
                "baseline에서 비교 가능한 loadcell 통계를 찾지 못했습니다.",
            )
        )

    interval = capture.get("settings", {}).get("interval_seconds")
    if isinstance(interval, (int, float)) and interval < 0.75:
        issues.append(
            issue(
                "WARN",
                "CAPTURE_INTERVAL_BELOW_THROTTLE",
                "수집 간격이 기본 loadcell throttle보다 짧아 cache frame이 반복될 수 있습니다.",
                details={"interval_seconds": interval, "recommended_minimum": 0.75},
            )
        )

    if len(samples) < thresholds.min_samples:
        issues.append(
            issue(
                "FAIL",
                "INSUFFICIENT_LOADCELL_SAMPLES",
                "판정에 필요한 loadcell sample이 부족합니다.",
                details={"actual": len(samples), "required": thresholds.min_samples},
            )
        )

    health = capture.get("health")
    if not isinstance(health, dict):
        issues.append(issue("FAIL", "HEALTH_UNAVAILABLE", "/health 응답을 받지 못했습니다."))
    else:
        for component in ("loadcells", "door", "deadbolt"):
            if health.get(component) != "HEALTHY":
                issues.append(
                    issue(
                        "FAIL",
                        "HEALTH_UNHEALTHY",
                        f"health 판정에서 {component}가 정상 상태가 아닙니다.",
                        details={"component": component, "value": health.get(component)},
                    )
                )

    product = capture.get("product_info")
    baseline_product = baseline.get("product_info") if isinstance(baseline, dict) else None
    if not isinstance(product, dict):
        issues.append(issue("FAIL", "PRODUCT_INFO_UNAVAILABLE", "장비 제조정보를 읽지 못했습니다."))
    elif isinstance(baseline_product, dict):
        if product.get("product_id") != baseline_product.get("product_id"):
            issues.append(
                issue(
                    "FAIL",
                    "PRODUCT_ID_CHANGED",
                    "baseline과 다른 IO Board가 연결되어 있습니다.",
                    details={
                        "baseline": baseline_product.get("product_id"),
                        "current": product.get("product_id"),
                    },
                )
            )
        if product.get("sw_version") != baseline_product.get("sw_version"):
            issues.append(
                issue(
                    "WARN",
                    "FIRMWARE_VERSION_CHANGED",
                    "baseline 이후 firmware version이 변경되었습니다.",
                    details={
                        "baseline": baseline_product.get("sw_version"),
                        "current": product.get("sw_version"),
                    },
                )
            )

    device_errors = capture.get("device_errors")
    if not isinstance(device_errors, dict):
        issues.append(issue("WARN", "ERROR_HISTORY_UNAVAILABLE", "장비 오류 이력을 읽지 못했습니다."))
    else:
        active_codes = [
            item.get("code")
            for item in device_errors.get("errors", [])
            if isinstance(item, dict) and item.get("code") not in (None, "0000")
        ]
        if active_codes:
            issues.append(
                issue(
                    "WARN",
                    "DEVICE_ERROR_HISTORY_PRESENT",
                    "장비 오류 이력에 코드가 남아 있습니다. 현재 고장 여부와 구분해 확인하십시오.",
                    details={"codes": active_codes},
                )
            )

    for stats in channels:
        channel = stats["channel"]
        error_rate = stats["error_rate"]
        error_count = sum(stats["error_counts"].values())
        if error_count:
            severity = "FAIL" if error_rate >= thresholds.marker_fail_rate else "WARN"
            issues.append(
                issue(
                    severity,
                    "LOADCELL_ERROR_MARKER",
                    "통신·범위 오류 또는 잘못된 loadcell 값이 관측되었습니다.",
                    channel=channel,
                    details={
                        "error_rate": error_rate,
                        "error_counts": stats["error_counts"],
                    },
                )
            )

        if stats["valid_count"] < thresholds.min_samples:
            issues.append(
                issue(
                    "FAIL",
                    "LOADCELL_VALID_SAMPLES_LOW",
                    "채널의 정상 판독 sample이 부족합니다.",
                    channel=channel,
                    details={"valid": stats["valid_count"], "required": thresholds.min_samples},
                )
            )
            continue

        stddev = stats["stddev"]
        value_range = stats["range"]
        if stddev is not None and stddev >= thresholds.noise_std_fail:
            severity = "FAIL"
        elif stddev is not None and stddev >= thresholds.noise_std_warn:
            severity = "WARN"
        else:
            severity = None
        if severity:
            issues.append(
                issue(
                    severity,
                    "LOADCELL_NOISY",
                    "정지 상태에서 채널 변동이 큽니다. 체결·배선·센서 접촉을 확인하십시오.",
                    channel=channel,
                    details={"stddev_grams": stddev},
                )
            )

        if value_range is not None and value_range >= thresholds.range_fail:
            range_severity = "FAIL"
        elif value_range is not None and value_range >= thresholds.range_warn:
            range_severity = "WARN"
        else:
            range_severity = None
        if range_severity:
            issues.append(
                issue(
                    range_severity,
                    "LOADCELL_RANGE_UNSTABLE",
                    "수집 구간의 채널 범위가 큽니다. 흔들림 또는 간헐 접촉을 확인하십시오.",
                    channel=channel,
                    details={"range_grams": value_range},
                )
            )

        if empty and stats["mean"] is not None:
            offset = abs(stats["mean"])
            if offset >= thresholds.empty_offset_fail:
                offset_severity = "FAIL"
            elif offset >= thresholds.empty_offset_warn:
                offset_severity = "WARN"
            else:
                offset_severity = None
            if offset_severity:
                issues.append(
                    issue(
                        offset_severity,
                        "EMPTY_ZERO_OFFSET",
                        "빈 선반 채널의 영점 편차가 큽니다. 기구 간섭 확인 후 calibration을 검토하십시오.",
                        channel=channel,
                        details={"mean_grams": stats["mean"]},
                    )
                )

        if base_channels and channel < len(base_channels):
            previous = base_channels[channel]
            base_mean = previous.get("mean")
            base_std = previous.get("stddev")
            if stats["mean"] is not None and isinstance(base_mean, (int, float)):
                shift = abs(stats["mean"] - base_mean)
                if shift >= thresholds.baseline_shift_fail:
                    shift_severity = "FAIL"
                elif shift >= thresholds.baseline_shift_warn:
                    shift_severity = "WARN"
                else:
                    shift_severity = None
                if shift_severity:
                    issues.append(
                        issue(
                            shift_severity,
                            "BASELINE_MEAN_SHIFT",
                            "이동 전 baseline 대비 채널 평균이 이동했습니다.",
                            channel=channel,
                            details={
                                "baseline_mean": base_mean,
                                "current_mean": stats["mean"],
                                "absolute_shift_grams": round(shift, 3),
                            },
                        )
                    )

            if stats["stddev"] is not None and isinstance(base_std, (int, float)):
                noise_floor = max(float(base_std), 1.0)
                ratio = stats["stddev"] / noise_floor
                if (
                    ratio >= thresholds.baseline_noise_ratio_fail
                    and stats["stddev"] >= thresholds.noise_std_warn
                ):
                    ratio_severity = "FAIL"
                elif (
                    ratio >= thresholds.baseline_noise_ratio_warn
                    and stats["stddev"] >= thresholds.noise_std_warn
                ):
                    ratio_severity = "WARN"
                else:
                    ratio_severity = None
                if ratio_severity:
                    issues.append(
                        issue(
                            ratio_severity,
                            "BASELINE_NOISE_INCREASED",
                            "이동 전 baseline 대비 채널 noise가 증가했습니다.",
                            channel=channel,
                            details={
                                "baseline_stddev": base_std,
                                "current_stddev": stats["stddev"],
                                "ratio": round(ratio, 3),
                            },
                        )
                    )

    status_samples = capture.get("status_samples", [])
    if not status_samples:
        issues.append(issue("FAIL", "STATUS_UNAVAILABLE", "door/deadbolt 상태를 읽지 못했습니다."))
    else:
        doors = [sample.get("door") for sample in status_samples]
        deadbolts = [sample.get("deadbolt") for sample in status_samples]
        invalid_doors = sorted(
            {value for value in doors if value not in {"OPENED", "CLOSED"}},
            key=str,
        )
        invalid_deadbolts = sorted(
            {value for value in deadbolts if value not in {"UNLOCK", "LOCKED"}},
            key=str,
        )
        if invalid_doors:
            issues.append(
                issue("FAIL", "DOOR_STATE_INVALID", "유효하지 않은 door 상태가 관측되었습니다.", details={"values": invalid_doors})
            )
        if invalid_deadbolts:
            issues.append(
                issue("FAIL", "DEADBOLT_STATE_INVALID", "유효하지 않은 deadbolt 상태가 관측되었습니다.", details={"values": invalid_deadbolts})
            )

        for label, values, expected in (
            ("door", doors, expected_door),
            ("deadbolt", deadbolts, expected_deadbolt),
        ):
            if expected is not None:
                mismatches = sum(value != expected for value in values)
                if mismatches:
                    severity = "FAIL" if mismatches == len(values) else "WARN"
                    issues.append(
                        issue(
                            severity,
                            f"{label.upper()}_EXPECTED_STATE_MISMATCH",
                            f"{label} 상태가 예상값과 일치하지 않습니다.",
                            details={
                                "expected": expected,
                                "mismatches": mismatches,
                                "samples": len(values),
                                "observed": sorted(set(values), key=str),
                            },
                        )
                    )
            elif len(set(values)) > 1:
                issues.append(
                    issue(
                        "WARN",
                        f"{label.upper()}_STATE_CHANGED",
                        f"정지 점검 중 {label} 상태가 변했습니다. 센서·connector 체결을 확인하십시오.",
                        details={"observed": sorted(set(values), key=str)},
                    )
                )

    requests = capture.get("requests", [])
    failures = [record for record in requests if not record.get("ok")]
    failure_rate = len(failures) / len(requests) if requests else 1.0
    if failures:
        severity = "FAIL" if failure_rate >= thresholds.request_failure_rate_fail else "WARN"
        issues.append(
            issue(
                severity,
                "API_REQUEST_FAILURES",
                "진단 중 API 요청 실패가 발생했습니다.",
                details={
                    "failures": len(failures),
                    "requests": len(requests),
                    "failure_rate": round(failure_rate, 6),
                    "paths": [record.get("path") for record in failures],
                },
            )
        )

    latencies = [
        float(record["latency_ms"])
        for record in requests
        if record.get("ok") and isinstance(record.get("latency_ms"), (int, float))
    ]
    p95 = percentile(latencies, 0.95)
    if p95 is not None:
        if p95 >= thresholds.latency_fail_ms:
            latency_severity = "FAIL"
        elif p95 >= thresholds.latency_warn_ms:
            latency_severity = "WARN"
        else:
            latency_severity = None
        if latency_severity:
            issues.append(
                issue(
                    latency_severity,
                    "API_LATENCY_HIGH",
                    "API 응답 지연이 큽니다. serial timeout·재시도 로그를 확인하십시오.",
                    details={"p95_latency_ms": round(p95, 3)},
                )
            )

    overall_rank = max((SEVERITY_RANK[item["severity"]] for item in issues), default=0)
    overall = {0: "PASS", 1: "WARN", 2: "FAIL"}[overall_rank]
    return {
        "overall": overall,
        "issues": issues,
        "channels": channels,
        "request_summary": {
            "requests": len(requests),
            "failures": len(failures),
            "failure_rate": round(failure_rate, 6),
            "p95_latency_ms": round(p95, 3) if p95 is not None else None,
        },
        "limitations": [
            "loadcell 값은 sanitizer와 throttle 적용 이후 값입니다.",
            "고정된 정상값만으로 sensor 감도 저하·완전 고착을 확정할 수 없습니다.",
            "장비 오류 이력은 과거 FIFO이며 현재 고장만을 뜻하지 않습니다.",
        ],
        "manual_checks": [
            "전원을 끈 뒤 loadcell·door·deadbolt connector와 체결부를 육안 확인합니다.",
            "각 선반에 알려진 분동을 순서대로 올려 채널 반응과 복귀를 확인합니다.",
            "빈 선반의 기구 간섭을 제거한 뒤에만 calibration을 수행합니다.",
        ],
    }


def save_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("baseline JSON root must be an object")
    return payload


def print_summary(report: dict[str, Any], output_path: str) -> None:
    analysis = report["analysis"]
    issues = analysis["issues"]
    counts = {
        severity: sum(item["severity"] == severity for item in issues)
        for severity in ("FAIL", "WARN")
    }
    print(f"\n[{analysis['overall']}] 이동 후 IO Board 진단")
    print(
        f"  loadcell samples={len(report.get('loadcell_samples', []))}, "
        f"fail={counts['FAIL']}, warn={counts['WARN']}"
    )
    for item in issues:
        channel = f" ch{item['channel']}" if "channel" in item else ""
        print(f"  - {item['severity']} {item['code']}{channel}: {item['message']}")
    if not issues:
        print("  - 자동 진단에서 이상이 발견되지 않았습니다.")
    print(f"  report: {output_path}")
    print("  주의: 고착·감도 저하는 알려진 분동을 사용한 수동 반응 시험이 필요합니다.")


def add_capture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default="http://localhost:8000", help="서비스 base URL")
    parser.add_argument("--duration", type=float, default=30.0, help="수집 시간(초)")
    parser.add_argument(
        "--interval",
        type=float,
        default=0.85,
        help="loadcell 수집 간격(초). 기본 throttle 0.75초보다 길게 유지",
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout(초)")
    parser.add_argument(
        "--status-every",
        type=int,
        default=5,
        help="loadcell N회마다 door/deadbolt 상태 수집",
    )


def add_threshold_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--marker-fail-rate", type=float, default=0.05)
    parser.add_argument("--noise-std-warn", type=float, default=5.0)
    parser.add_argument("--noise-std-fail", type=float, default=15.0)
    parser.add_argument("--range-warn", type=float, default=20.0)
    parser.add_argument("--range-fail", type=float, default=50.0)
    parser.add_argument("--empty-offset-warn", type=float, default=50.0)
    parser.add_argument("--empty-offset-fail", type=float, default=200.0)
    parser.add_argument("--baseline-shift-warn", type=float, default=20.0)
    parser.add_argument("--baseline-shift-fail", type=float, default=100.0)
    parser.add_argument("--baseline-noise-ratio-warn", type=float, default=3.0)
    parser.add_argument("--baseline-noise-ratio-fail", type=float, default=5.0)
    parser.add_argument("--latency-warn-ms", type=float, default=1000.0)
    parser.add_argument("--latency-fail-ms", type=float, default=2500.0)
    parser.add_argument("--request-failure-rate-fail", type=float, default=0.10)


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_samples=args.min_samples,
        marker_fail_rate=args.marker_fail_rate,
        noise_std_warn=args.noise_std_warn,
        noise_std_fail=args.noise_std_fail,
        range_warn=args.range_warn,
        range_fail=args.range_fail,
        empty_offset_warn=args.empty_offset_warn,
        empty_offset_fail=args.empty_offset_fail,
        baseline_shift_warn=args.baseline_shift_warn,
        baseline_shift_fail=args.baseline_shift_fail,
        baseline_noise_ratio_warn=args.baseline_noise_ratio_warn,
        baseline_noise_ratio_fail=args.baseline_noise_ratio_fail,
        latency_warn_ms=args.latency_warn_ms,
        latency_fail_ms=args.latency_fail_ms,
        request_failure_rate_fail=args.request_failure_rate_fail,
    )


def validate_args(args: argparse.Namespace) -> None:
    if args.duration <= 0 or args.interval <= 0 or args.timeout <= 0:
        raise ValueError("duration, interval and timeout must be positive")
    if args.status_every < 1 or args.min_samples < 1:
        raise ValueError("status-every and min-samples must be at least 1")
    for name in (
        "marker_fail_rate",
        "request_failure_rate_fail",
    ):
        value = getattr(args, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name.replace('_', '-')} must be between 0 and 1")
    ordered_pairs = (
        ("noise_std_warn", "noise_std_fail"),
        ("range_warn", "range_fail"),
        ("empty_offset_warn", "empty_offset_fail"),
        ("baseline_shift_warn", "baseline_shift_fail"),
        ("baseline_noise_ratio_warn", "baseline_noise_ratio_fail"),
        ("latency_warn_ms", "latency_fail_ms"),
    )
    for warn_name, fail_name in ordered_pairs:
        warn_value = getattr(args, warn_name)
        fail_value = getattr(args, fail_name)
        if warn_value < 0 or fail_value < warn_value:
            raise ValueError(
                f"{fail_name.replace('_', '-')} must be greater than or equal to "
                f"{warn_name.replace('_', '-')}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    baseline_parser = subparsers.add_parser("baseline", help="이동 전 기준값 저장")
    add_capture_options(baseline_parser)
    add_threshold_options(baseline_parser)
    baseline_parser.add_argument("-o", "--out", required=True, help="baseline JSON 경로")
    baseline_parser.add_argument("--empty", action="store_true", help="빈 선반 영점 기준 적용")
    baseline_parser.add_argument("--expect-door", choices=["OPENED", "CLOSED"])
    baseline_parser.add_argument("--expect-deadbolt", choices=["UNLOCK", "LOCKED"])

    check_parser = subparsers.add_parser("check", help="이동 후 상태 점검")
    add_capture_options(check_parser)
    add_threshold_options(check_parser)
    check_parser.add_argument("--baseline", help="이동 전 baseline JSON")
    check_parser.add_argument("--report", help="결과 JSON 경로")
    check_parser.add_argument("--empty", action="store_true", help="빈 선반 영점 기준 적용")
    check_parser.add_argument("--expect-door", choices=["OPENED", "CLOSED"])
    check_parser.add_argument("--expect-deadbolt", choices=["UNLOCK", "LOCKED"])

    args = parser.parse_args()
    try:
        validate_args(args)
        thresholds = thresholds_from_args(args)
        baseline = load_json(args.baseline) if getattr(args, "baseline", None) else None
        capture = collect(
            args.url,
            args.duration,
            args.interval,
            args.timeout,
            args.status_every,
        )
        capture["kind"] = "pre-move-baseline" if args.command == "baseline" else "post-move-check"
        capture["diagnostic_context"] = {
            "empty_shelves": args.empty,
            "expected_door": args.expect_door,
            "expected_deadbolt": args.expect_deadbolt,
            "baseline_path": getattr(args, "baseline", None),
        }
        capture["thresholds"] = asdict(thresholds)
        capture["analysis"] = analyze(
            capture,
            thresholds=thresholds,
            baseline=baseline,
            empty=args.empty,
            expected_door=args.expect_door,
            expected_deadbolt=args.expect_deadbolt,
        )

        if args.command == "baseline":
            output_path = args.out
        else:
            output_path = args.report or f"post_move_report_{datetime.now():%Y%m%d_%H%M%S}.json"
        save_json(output_path, capture)
        print_summary(capture, output_path)
        return {"PASS": 0, "WARN": 1, "FAIL": 2}[capture["analysis"]["overall"]]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
