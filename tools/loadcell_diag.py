#!/usr/bin/env python3
"""로드셀 부호 왕복(±N 플리커) 진단 스크립트.

GET /loadcells 를 고속 폴링해 10채널 시계열을 수집하고,
세 가지 가설을 판별한다:

  A. 간섭/진동  — 매 샘플 규칙적 반전(나이퀴스트 진동). 참값은 평균(≈0).
  B. 부호 비트 손상 — 크기는 유지, 부호 반전이 불규칙(레이스성).
  C. 주소 충돌/채널 인터리브 — 다른 셀 값이 번갈아 유입.
     같은 선반 짝 채널에 미러(-v) 패턴, 존 합은 불변.

사용법:
  python3 loadcell_diag.py capture -o flicker.jsonl --duration 60 --interval 0.05
  python3 loadcell_diag.py analyze flicker.jsonl
  python3 loadcell_diag.py run -o flicker.jsonl --duration 60   # 수집 후 바로 분석

표준 라이브러리만 사용. 엣지 장비에 파일 하나만 복사하면 됨.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request

ERROR_VALUES = ("EEEEEE", "VVVVVV")


# ---------------------------------------------------------------- capture

def capture(url: str, out_path: str, duration: float, interval: float) -> None:
    end = time.time() + duration
    n = 0
    errors = 0
    with open(out_path, "w") as f:
        while time.time() < end:
            t0 = time.time()
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    payload = json.loads(resp.read())
                row = {"ts": t0, "loadcells": payload["loadcells"]}
            except Exception as e:  # noqa: BLE001 - 수집 루프는 계속 돌아야 함
                row = {"ts": t0, "error": str(e)}
                errors += 1
            f.write(json.dumps(row) + "\n")
            n += 1
            if n % 100 == 0:
                print(f"  {n} samples ({errors} errors)...", file=sys.stderr)
            time.sleep(max(0.0, interval - (time.time() - t0)))
    print(f"capture done: {n} samples, {errors} errors -> {out_path}", file=sys.stderr)


# ---------------------------------------------------------------- parsing

def parse_value(s: str) -> float | None:
    if s in ERROR_VALUES:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load_series(path: str) -> tuple[list[float], list[list[float | None]]]:
    """JSONL -> (timestamps, series[channel][sample])."""
    ts: list[float] = []
    rows: list[list[float | None]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "loadcells" not in row:
                continue
            ts.append(row["ts"])
            rows.append([parse_value(v) for v in row["loadcells"]])
    if not rows:
        raise SystemExit("no valid samples in file")
    n_ch = len(rows[0])
    series = [[r[i] for r in rows] for i in range(n_ch)]
    return ts, series


# ---------------------------------------------------------------- analysis

def mean_std(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return (float("nan"), float("nan"))
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return m, math.sqrt(var)


def pearson(a: list[float], b: list[float]) -> float:
    if len(a) < 3:
        return float("nan")
    ma, sa = mean_std(a)
    mb, sb = mean_std(b)
    if sa == 0 or sb == 0:
        return float("nan")
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)
    return cov / (sa * sb)


def analyze(path: str, mag_tol: float, min_mag: float, pairs: list[tuple[int, int]]) -> None:
    ts, series = load_series(path)
    n_ch = len(series)
    n = len(ts)
    dt = [(ts[i + 1] - ts[i]) for i in range(n - 1)]
    dt_m, dt_s = mean_std(dt)
    print(f"samples: {n}, channels: {n_ch}, poll interval: {dt_m*1000:.0f}±{dt_s*1000:.0f} ms")
    print()

    flappy: list[int] = []

    print("=" * 78)
    print("[1] 채널별 부호 반전(등크기) 통계")
    print("=" * 78)
    for ch in range(n_ch):
        v = series[ch]
        valid = [x for x in v if x is not None]
        if not valid:
            print(f"ch{ch}: all error values")
            continue
        m, s = mean_std(valid)

        flips = []          # (sample index, magnitude)
        transitions = 0
        for i in range(1, n):
            a, b = v[i - 1], v[i]
            if a is None or b is None:
                continue
            transitions += 1
            if (
                abs(abs(a) - abs(b)) <= mag_tol
                and abs(a) >= min_mag
                and a * b < 0
            ):
                flips.append((i, abs(b)))

        line = (
            f"ch{ch}: mean={m:+8.2f} std={s:7.2f} "
            f"min={min(valid):+8.1f} max={max(valid):+8.1f} "
            f"sign-flips={len(flips)}/{transitions}"
        )
        if flips:
            flappy.append(ch)
            mags = sorted({round(mg, 1) for _, mg in flips})
            idxs = [i for i, _ in flips]
            gaps = [idxs[k + 1] - idxs[k] for k in range(len(idxs) - 1)]
            gap_m, gap_s = mean_std([float(g) for g in gaps]) if gaps else (float("nan"), float("nan"))
            # 반전 구간에서 +/− 비율 (해당 크기 근처 샘플만)
            flap_mag = mags[-1]
            near = [x for x in valid if abs(abs(x) - flap_mag) <= mag_tol]
            pos = sum(1 for x in near if x > 0)
            duty = pos / len(near) if near else float("nan")
            line += (
                f"\n      flap magnitudes={mags}"
                f" | flip gap: {gap_m:.2f}±{gap_s:.2f} samples"
                f" | +부호 비율(duty)={duty:.2f}"
            )
            if gaps and gap_m < 1.5 and gap_s < 0.6:
                line += "\n      -> 매 샘플 규칙 반전: 가설 A(진동/간섭) 서명. 2-탭 평균으로 소거 가능"
            elif gaps and gap_s / max(gap_m, 1e-9) > 0.5:
                line += "\n      -> 불규칙 반전: 가설 B(부호 비트 손상) 쪽 서명"
        print(line)
    print()

    if not flappy:
        print("부호 반전 채널 없음 — 플리커가 재현된 구간인지 확인 필요.")
        return

    print("=" * 78)
    print("[2] 미러 채널 검사 (가설 C: 다른 셀 값 인터리브)")
    print("=" * 78)
    found_mirror = False
    for ch in flappy:
        v = series[ch]
        for other in range(n_ch):
            if other == ch:
                continue
            w = series[other]
            both = [
                (a, b) for a, b in zip(v, w)
                if a is not None and b is not None and abs(a) >= min_mag
            ]
            if len(both) < 5:
                continue
            mirror = sum(1 for a, b in both if abs(a + b) <= mag_tol) / len(both)
            corr = pearson([a for a, _ in both], [b for _, b in both])
            if mirror >= 0.5 or (not math.isnan(corr) and corr <= -0.6):
                found_mirror = True
                print(
                    f"ch{ch} vs ch{other}: mirror(v_j≈-v_i) 비율={mirror:.2f}, "
                    f"corr={corr:+.2f}  <-- 미러 후보!"
                )
    if not found_mirror:
        print("미러 채널 없음 -> 가설 C 기각 근거")
    print()

    print("=" * 78)
    print("[3] 존(짝 채널) 합계 안정성 — 개별 std 대비 합계 std")
    print("=" * 78)
    for i, j in pairs:
        if i >= n_ch or j >= n_ch:
            continue
        both = [
            (a, b) for a, b in zip(series[i], series[j])
            if a is not None and b is not None
        ]
        if len(both) < 5:
            continue
        _, si = mean_std([a for a, _ in both])
        _, sj = mean_std([b for _, b in both])
        sm, ss = mean_std([a + b for a, b in both])
        note = ""
        if ss < 0.5 * max(si, sj) and max(si, sj) >= min_mag:
            note = "  <-- 개별은 요동, 합은 안정: 재분배/인터리브 서명"
        print(
            f"zone({i},{j}): std(ch{i})={si:6.2f} std(ch{j})={sj:6.2f} "
            f"sum={sm:+8.2f}±{ss:.2f}{note}"
        )
    print()

    print("=" * 78)
    print("[4] 프레임 일괄 반전 검사 (전 채널 동시 부호 반전)")
    print("=" * 78)
    # 1단계: 인접 프레임 상대 비교 — 프레임 k가 k-1의 음화인지, 유의미 채널의
    #         중앙값 오차(err_neg vs err_same)로 판정. 특정 "기준 프레임"에 의존하지
    #         않아 한 번의 오판이 뒤로 전파되지 않는다.
    # 2단계: 상대 반전을 적분해 프레임별 방향(orientation)을 얻고,
    #         다수 방향을 정상으로 놓는다 (참값은 다수 쪽이라는 가정).
    def median(xs: list[float]) -> float:
        ys = sorted(xs)
        return ys[len(ys) // 2]

    flip_rel = [False] * n
    for k in range(1, n):
        both = [
            (a, b)
            for a, b in zip(
                (series[ch][k - 1] for ch in range(n_ch)),
                (series[ch][k] for ch in range(n_ch)),
            )
            if a is not None and b is not None
            and (abs(a) >= min_mag or abs(b) >= min_mag)
        ]
        if both:
            err_same = median([abs(b - a) for a, b in both])
            err_neg = median([abs(b + a) for a, b in both])
            flip_rel[k] = err_neg < err_same

    inverted = [False] * n
    for k in range(1, n):
        inverted[k] = inverted[k - 1] ^ flip_rel[k]
    if sum(inverted) > n / 2:
        inverted = [not x for x in inverted]

    n_inv = sum(inverted)
    print(f"반전 프레임: {n_inv}/{n} ({n_inv/n*100:.1f}%)")
    if n_inv:
        bursts = []
        run = 0
        for flag in inverted + [False]:
            if flag:
                run += 1
            elif run:
                bursts.append(run)
                run = 0
        bm, bs = mean_std([float(b) for b in bursts])
        print(f"버스트 수: {len(bursts)}, 길이: {bm:.2f}±{bs:.2f} 샘플 (최대 {max(bursts)})")

        # 반전 프레임을 되뒤집어 복구했을 때 채널별 std가 얼마나 줄어드는지
        print("복구(반전 프레임 negate) 후 채널별 std:")
        for ch in range(n_ch):
            orig = [x for x in series[ch] if x is not None]
            fixed = [
                (-x if inverted[k] else x)
                for k, x in enumerate(series[ch]) if x is not None
            ]
            _, so = mean_std(orig)
            _, sf = mean_std(fixed)
            print(f"  ch{ch}: std {so:8.2f} -> {sf:8.2f}")
        print("-> 복구 후 std가 노이즈 수준(수 g)으로 떨어지면 '프레임 일괄 반전' 확정.")
        print("   처방: 엣지 관문에서 프레임 negation 감지 시 되뒤집기 (정보 손실 없음).")
    else:
        print("-> 프레임 일괄 반전 없음. [1]의 채널별 결과로 A/B 판별.")
    print()

    print("=" * 78)
    print("[5] 판별 요약")
    print("=" * 78)
    print("""\
- [1]에서 flip gap ≈ 1.0 샘플로 규칙적이면        -> A: 간섭/진동. 처방: 2-탭 이동평균.
- [1]에서 반전이 불규칙(gap 산포 큼)이면          -> B: 부호 비트 손상. 처방: 크기 신뢰 + 부호 연속성 필터.
- [2]에 미러 후보가 있거나 [3]에서 합만 안정이면  -> C: 주소 충돌/인터리브. 처방: 센서 주소 재할당(엣지 필터 불필요).
- [4]에서 반전 프레임 검출 + 복구 후 std 급감이면 -> 프레임 일괄 반전. 처방: 관문에서 negation 감지 시 되뒤집기.
추가 판별(권장): 해당 채널에 기지 무게 W를 올리고 재수집 —
  W±A로 흔들리고 부호 안 뒤집힘 -> A 확정 / ±W로 부호만 반전 -> B 확정.""")


# ---------------------------------------------------------------- main

def parse_pairs(s: str) -> list[tuple[int, int]]:
    out = []
    for part in s.split(","):
        i, j = part.split("-")
        out.append((int(i), int(j)))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common_capture(sp):
        sp.add_argument("--url", default="http://localhost:8000/loadcells")
        sp.add_argument("--duration", type=float, default=60.0, help="수집 시간(초)")
        sp.add_argument("--interval", type=float, default=0.05, help="폴링 간격(초)")
        sp.add_argument("-o", "--out", default="loadcell_capture.jsonl")

    def add_common_analyze(sp):
        sp.add_argument("--mag-tol", type=float, default=2.0, help="등크기 판정 허용오차(g)")
        sp.add_argument("--min-mag", type=float, default=5.0, help="반전으로 볼 최소 크기(g)")
        sp.add_argument(
            "--pairs", type=parse_pairs, default=parse_pairs("0-1,2-3,4-5,6-7,8-9"),
            help="존 짝 채널 (예: 0-1,2-3,...) — 실제 배선에 맞게 지정",
        )

    sp_c = sub.add_parser("capture", help="폴링 수집만")
    add_common_capture(sp_c)

    sp_a = sub.add_parser("analyze", help="수집 파일 분석만")
    sp_a.add_argument("file")
    add_common_analyze(sp_a)

    sp_r = sub.add_parser("run", help="수집 후 바로 분석")
    add_common_capture(sp_r)
    add_common_analyze(sp_r)

    args = p.parse_args()
    if args.cmd == "capture":
        capture(args.url, args.out, args.duration, args.interval)
    elif args.cmd == "analyze":
        analyze(args.file, args.mag_tol, args.min_mag, args.pairs)
    else:
        capture(args.url, args.out, args.duration, args.interval)
        analyze(args.out, args.mag_tol, args.min_mag, args.pairs)


if __name__ == "__main__":
    main()
