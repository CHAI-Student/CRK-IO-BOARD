"""
Unit tests for the loadcell sanitizer (sign-glitch correction + quantization).

INSTALLATION:
1. Create 'tests' directory in project root
2. Move this file to tests/test_sanitizer.py
3. Install: pip install pytest
4. Run: pytest tests/test_sanitizer.py

Covers the firmware sign-glitch defect from issue #1: single-frame,
magnitude-preserving sign inversions walking across channels.
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.config import SanitizeModel
from services.io_board.sanitizer import LoadcellSanitizer


def make(quantize: float = 0.0, **overrides) -> LoadcellSanitizer:
    return LoadcellSanitizer(SanitizeModel(quantize_grams=quantize, **overrides))


def frame(*values: str) -> list[str]:
    """Pad a partial frame to 10 channels with zeros."""
    return list(values) + ["+00000"] * (10 - len(values))


class TestSignGlitchCorrection:
    def test_single_frame_glitch_is_corrected(self):
        s = make()
        s.sanitize(frame("+00962"), now=0.0)
        out = s.sanitize(frame("-00962"), now=0.1)
        assert out[0] == "+00962"

    def test_glitch_correction_preserves_fresh_magnitude(self):
        s = make()
        s.sanitize(frame("+00962"), now=0.0)
        # 크기가 1g 흘러도(허용오차 내) 새 크기를 유지한 채 부호만 복원
        out = s.sanitize(frame("-00963"), now=0.1)
        assert out[0] == "+00963"

    def test_walking_glitch_across_channels(self):
        # issue #1 실측 패턴: 음수 슬롯이 채널을 한 칸씩 순회
        s = make()
        base = ["+00962", "+00522", "+00520", "+00519", "+00129",
                "+00052", "+00696", "+00080", "+00084", "+00552"]
        s.sanitize(list(base), now=0.0)
        for k, ch in enumerate([6, 7, 8, 9, 0, 1]):
            glitched = list(base)
            glitched[ch] = "-" + base[ch][1:]
            out = s.sanitize(glitched, now=0.1 * (k + 1))
            assert out == base, f"walking glitch at ch{ch} not corrected"

    def test_persistent_flip_is_relatched(self):
        # 반전이 relatch_frames(3) 연속 지속되면 진짜 변화로 수용
        s = make()
        s.sanitize(frame("+00100"), now=0.0)
        assert s.sanitize(frame("-00100"), now=0.1)[0] == "+00100"
        assert s.sanitize(frame("-00100"), now=0.2)[0] == "+00100"
        assert s.sanitize(frame("-00100"), now=0.3)[0] == "-00100"
        # 수용 후에는 계속 그대로
        assert s.sanitize(frame("-00100"), now=0.4)[0] == "-00100"

    def test_real_weight_change_passes_through(self):
        s = make()
        s.sanitize(frame("+00130"), now=0.0)
        out = s.sanitize(frame("+00391"), now=0.1)  # 실측 ch4의 실제 스텝
        assert out[4 - 4] == "+00391"

    def test_zero_crossing_noise_not_corrected(self):
        # |v| < min_magnitude_grams(5): 영점 노이즈는 건드리지 않음
        s = make()
        s.sanitize(frame("+00002"), now=0.0)
        out = s.sanitize(frame("-00002"), now=0.1)
        assert out[0] == "-00002"

    def test_different_magnitude_sign_change_not_corrected(self):
        # 크기가 다른 부호 전환은 진짜 변화
        s = make()
        s.sanitize(frame("+00100"), now=0.0)
        out = s.sanitize(frame("-00030"), now=0.1)
        assert out[0] == "-00030"

    def test_stale_previous_value_not_used(self):
        s = make()
        s.sanitize(frame("+00962"), now=0.0)
        out = s.sanitize(frame("-00962"), now=10.0)  # staleness 2s 초과
        assert out[0] == "-00962"

    def test_error_values_pass_through(self):
        s = make()
        s.sanitize(frame("+00962"), now=0.0)
        out = s.sanitize(frame("EEEEEE", "VVVVVV"), now=0.1)
        assert out[0] == "EEEEEE" and out[1] == "VVVVVV"
        # 에러 후 복귀한 값과 이전 값의 비교는 여전히 유효
        out = s.sanitize(frame("-00962"), now=0.2)
        assert out[0] == "+00962"

    def test_reset_clears_state(self):
        s = make()
        s.sanitize(frame("+00962"), now=0.0)
        s.reset()
        out = s.sanitize(frame("-00962"), now=0.1)
        assert out[0] == "-00962"


class TestMedianFilterOption:
    """median_filter=True (스로틀 비활성 시의 레거시 방어) 전용 동작."""

    def test_glitch_during_real_step_not_mislatched(self):
        # 실제 스텝(130->390)과 같은 프레임에 글리치(-390)가 겹치는 케이스 —
        # 가드 단독으론 반전 락이 걸리지만 미디언은 흡수한다 (1프레임 지연 비용)
        s = make(median_filter=True)
        s.sanitize(frame("+00130"), now=0.0)
        s.sanitize(frame("+00130"), now=0.1)
        out3 = s.sanitize(frame("-00390"), now=0.2)   # 글리치+스텝 동시
        out4 = s.sanitize(frame("+00390"), now=0.3)
        out5 = s.sanitize(frame("+00390"), now=0.4)
        assert out3[0] == "+00130"   # 글리치 프레임은 직전 값으로 흡수
        assert out5[0] == "+00390"   # 스텝은 1프레임 지연 후 통과

    def test_median_adds_one_frame_latency(self):
        s = make(median_filter=True)
        s.sanitize(frame("+00130"), now=0.0)
        s.sanitize(frame("+00130"), now=0.1)
        out = s.sanitize(frame("+00390"), now=0.2)
        assert out[0] == "+00130"    # 미디언 창이 스텝을 한 프레임 지연

    def test_default_has_no_latency(self):
        s = make()
        s.sanitize(frame("+00130"), now=0.0)
        s.sanitize(frame("+00130"), now=0.1)
        out = s.sanitize(frame("+00390"), now=0.2)
        assert out[0] == "+00390"    # 기본(가드만): 지연 없음


class TestQuantization:
    def test_half_up_rounding_matches_math_round(self):
        s = make(quantize=5.0)
        # (입력, 기대값) — JS Math.round(x/5)*5 와 동일해야 함
        cases = [
            ("+00024", "+00025"), ("+00022", "+00020"),
            ("-00024", "-00025"), ("-00022", "-00020"),
            ("+00002", "+00000"), ("-00002", "+00000"),  # 음의 영 없음
            ("+00025", "+00025"), ("+00000", "+00000"),
        ]
        for raw, expected in cases:
            s.reset()
            out = s.sanitize(frame(raw), now=0.0)
            assert out[0] == expected, f"{raw} -> {out[0]}, expected {expected}"

    def test_quantize_disabled_keeps_original_string(self):
        s = make(quantize=0.0)
        out = s.sanitize(frame("+00024"), now=0.0)
        assert out[0] == "+00024"

    def test_bin_boundary_flapping_suppressed(self):
        # 원시 962<->963 (±1g 노이즈가 962.5 경계에 걸침) — 출력 bin은 고정
        s = make(quantize=5.0)
        outs = set()
        for k, raw in enumerate(["+00962", "+00963", "+00962", "+00963", "+00962"]):
            outs.add(s.sanitize(frame(raw), now=0.1 * k)[0])
        assert len(outs) == 1

    def test_real_step_leaves_bin_immediately(self):
        s = make(quantize=5.0)
        s.sanitize(frame("+00130"), now=0.0)
        out = s.sanitize(frame("+00390"), now=0.1)
        assert out[0] == "+00390"

    def test_glitch_check_uses_unquantized_values(self):
        # 양자화가 켜져 있어도 글리치 판정은 원본 크기로 수행
        s = make(quantize=5.0)
        s.sanitize(frame("+00962"), now=0.0)
        out = s.sanitize(frame("-00961"), now=0.1)
        assert out[0] == "+00960"  # 부호 복원 + 5g 양자화


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
