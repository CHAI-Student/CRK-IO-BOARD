"""loadcell 판독값 sanitizer (sign-glitch 보정 + quantization).

펌웨어/MCU 결함 대응 모듈: RQIW 응답의 약 12%에서 특정 채널의 부호만
반전된 판독값이 내려온다. 크기(magnitude)는 보존되고, 손상은 채널당
정확히 1 frame만 지속되며, 손상 슬롯이 채널을 한 칸씩 순회한다
(issue #1 캡처: glitch 781/782건이 단일 frame, 크기 차이 중앙값 0.0g).

채널별 복구는 두 layer로 구성된다:

1. (옵션, ``median_filter``) 원시 판독값에 대한 median-of-3
   (출력 1 frame 지연). glitch가 정확히 1 frame이므로 부호/크기와
   무관하게 제거되고, 실제 무게 step과 glitch가 같은 frame에 겹치는
   경우(부호 규칙만으로는 오판)도 흡수한다. request throttle
   (``polling.loadcells_min_request_gap`` >= ~0.7s)이 소스 단계에서
   부호를 깨끗하게 유지하므로 기본값은 OFF다: 0.8s 샘플링에서
   1 frame 지연은 제거할 glitch도 없이 0.8s의 plateau 타이밍만
   희생시킨다. throttle을 끌 때만 켤 것.
2. 부호 연속성 guard (항상 ON): 직전 출력의 부호 반전 근사값
   (크기 차이가 tolerance 이내)을 원래 부호로 되돌린다. ~0.7s 손상
   임계치가 온도/트래픽으로 drift할 경우의 잔여 보험이며, 보정
   카운터는 재발 telemetry 역할도 한다. 반전 부호가
   ``relatch_frames`` frame 연속 지속되면 실제 변화로 수용한다.

추가로 센서 보증 resolution(LABD-B3/K3 스펙: division 1g, resolution
5g)으로 출력을 quantize할 수 있다. 향후 펌웨어 측 구현
``Math.round(raw / 5) * 5``와 일치하도록 half-up 반올림을 사용한다.
"""

import math
import time
from typing import Optional

from core.config import SanitizeModel
from core.logging_config import get_logger

logger = get_logger(__name__)

ERROR_VALUES = ("EEEEEE", "VVVVVV")


class LoadcellSanitizer:
    """채널별 상태를 유지하며 sign-glitch 보정과 resolution quantization을 수행."""

    def __init__(self, config: SanitizeModel, channels: int = 10):
        self._config = config
        self._channels = channels
        self._window: list[list[float]] = [[] for _ in range(channels)]
        self._prev: list[Optional[float]] = [None] * channels
        self._prev_ts: list[float] = [0.0] * channels
        self._flip_streak: list[int] = [0] * channels
        self._prev_bin: list[Optional[float]] = [None] * channels
        self._glitch_count = 0

    def reset(self) -> None:
        """모든 채널 상태 초기화 (예: 디바이스 재연결 후)."""
        self._window = [[] for _ in range(self._channels)]
        self._prev = [None] * self._channels
        self._prev_ts = [0.0] * self._channels
        self._flip_streak = [0] * self._channels
        self._prev_bin = [None] * self._channels

    def sanitize(self, values: list[str], now: Optional[float] = None) -> list[str]:
        """loadcell 판독값 1 frame을 sanitize한다.

        Args:
            values: 디바이스에서 수신한 원시 판독값 ("+XXXXX" 형식 또는
                "EEEEEE"/"VVVVVV" 에러 마커).
            now: 테스트용 주입 가능한 clock. 기본값은 time.monotonic().

        Returns:
            입력과 동일한 길이/형식의 sanitize된 판독값.
            에러 마커는 그대로 통과한다.
        """
        cfg = self._config
        ts = time.monotonic() if now is None else now
        out: list[str] = []

        for i, raw in enumerate(values[: self._channels]):
            numeric = self._parse(raw)
            if numeric is None:
                out.append(raw)
                continue

            prev = self._prev[i]
            fresh = (ts - self._prev_ts[i]) <= cfg.staleness_seconds

            # Layer 1 (옵션): median-of-3가 단일 frame outlier를 제거
            # (window가 채워진 뒤에는 1 frame 지연 비용 발생).
            if cfg.median_filter:
                if not fresh:
                    self._window[i] = []
                self._window[i].append(numeric)
                if len(self._window[i]) > 3:
                    self._window[i].pop(0)
                if len(self._window[i]) == 3:
                    value = sorted(self._window[i])[1]
                else:
                    value = numeric
            else:
                value = numeric

            # Layer 2: 부호 연속성 guard (항상 ON).
            if (
                prev is not None
                and fresh
                and value * prev < 0
                and abs(value) >= cfg.min_magnitude_grams
                and abs(abs(value) - abs(prev)) <= cfg.magnitude_tolerance_grams
            ):
                self._flip_streak[i] += 1
                if self._flip_streak[i] < cfg.relatch_frames:
                    # 크기는 신뢰할 수 있고 부호만 손상 —
                    # 직전 부호로 복원한다.
                    value = -value
                    self._glitch_count += 1
                    logger.debug(
                        f"Sign glitch corrected: ch={i} raw={raw} -> {value:+g} "
                        f"(total={self._glitch_count})"
                    )
                else:
                    # 반전 부호가 relatch_frames 연속 지속: 실제 변화로 수용.
                    self._flip_streak[i] = 0
            else:
                self._flip_streak[i] = 0

            self._prev[i] = value
            self._prev_ts[i] = ts

            quantized = self._quantize(i, value)
            if quantized == numeric:
                out.append(raw)  # 변경 없는 판독값은 원본 문자열 유지
            else:
                out.append(self._format(quantized))

        # 설정된 채널 수를 넘는 값은 (방어적으로) 그대로 통과시킨다.
        out.extend(values[self._channels:])
        return out

    @staticmethod
    def _parse(raw: str) -> Optional[float]:
        if raw in ERROR_VALUES:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _quantize(self, ch: int, value: float) -> float:
        step = self._config.quantize_grams
        if step <= 0:
            return value
        # Hysteresis: 판독값이 현재 bin을 확실히 벗어나기 전까지는 bin을
        # 유지한다. bin 경계에 걸친 노이즈가 인접 bin 사이를 오가며
        # 출력을 flapping시키는 것을 방지 (예: 원시 962<->963이
        # 960<->965로 flapping).
        prev_bin = self._prev_bin[ch]
        if (
            prev_bin is not None
            and abs(value - prev_bin)
            <= step / 2 + self._config.quantize_hysteresis_grams
        ):
            return prev_bin
        # Half-up 반올림 (Math.round 의미론). 예정된 펌웨어 측 구현과
        # 대칭을 이룬다. Python round()는 banker's rounding이라
        # 정확한 half-step에서 결과가 달라진다.
        quantized = math.floor(value / step + 0.5) * step
        self._prev_bin[ch] = quantized
        return quantized

    @staticmethod
    def _format(value: float) -> str:
        sign = "+" if value >= 0 else "-"
        return f"{sign}{min(abs(int(value)), 99999):05d}"


# 모듈 레벨 singleton. 애플리케이션 startup 시 설정된다
# (serial_io.configure_serial과 동일한 패턴).
_sanitizer: Optional[LoadcellSanitizer] = None


def configure_sanitizer(config: SanitizeModel) -> None:
    """loadcell sanitizer를 설정한다. startup 시 1회 호출."""
    global _sanitizer
    _sanitizer = LoadcellSanitizer(config) if config.enabled else None
    logger.info(
        "Loadcell sanitizer "
        + (
            f"enabled: tol={config.magnitude_tolerance_grams}g "
            f"min_mag={config.min_magnitude_grams}g "
            f"relatch={config.relatch_frames} frames "
            f"quantize={config.quantize_grams}g"
            if config.enabled
            else "disabled"
        )
    )


def sanitize_loadcells(values: list[str]) -> list[str]:
    """설정된 sanitizer를 적용한다. 미설정/비활성이면 no-op."""
    if _sanitizer is None:
        return values
    return _sanitizer.sanitize(values)


def reset_sanitizer() -> None:
    """보정 또는 재연결 후 sanitizer의 이전 판독값을 폐기한다."""
    if _sanitizer is not None:
        _sanitizer.reset()
