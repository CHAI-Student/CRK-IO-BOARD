"""
Loadcell reading sanitizer.

Works around a firmware/MCU defect where ~12% of RQIW responses carry a
sign-corrupted reading: the corrupted channel's magnitude is preserved but
its sign is inverted, the corruption lasts exactly one frame per channel,
and the affected scan slot walks across channels (see issue #1 capture:
781/782 glitch runs were single-frame, magnitude diff median 0.0 g).

Recovery, per channel, two layers:

1. Median-of-3 over the raw readings (one-frame output latency). Because
   glitches last exactly one frame, the median removes them regardless of
   sign or magnitude — including a glitch that coincides with a genuine
   weight step, where a sign-only rule would mis-latch.
2. Sign-continuity guard on the median output: a value that is
   approximately the negation of the previous output (magnitude within
   tolerance) is corrected back, covering the rare two-frame glitch run
   the median lets through. If the inverted sign persists for
   ``relatch_frames`` consecutive frames it is accepted as genuine.

Optionally quantizes output to the sensor's guaranteed resolution
(LABD-B3/K3 spec: division 1 g, resolution 5 g) using half-up rounding to
match a future firmware-side ``Math.round(raw / 5) * 5``.
"""

import math
import time
from typing import Optional

from core.config import SanitizeModel
from core.logging_config import get_logger

logger = get_logger(__name__)

ERROR_VALUES = ("EEEEEE", "VVVVVV")


class LoadcellSanitizer:
    """Stateful per-channel sign-glitch correction + resolution quantization."""

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
        """Drop all channel state (e.g., after device reconnect)."""
        self._window = [[] for _ in range(self._channels)]
        self._prev = [None] * self._channels
        self._prev_ts = [0.0] * self._channels
        self._flip_streak = [0] * self._channels
        self._prev_bin = [None] * self._channels

    def sanitize(self, values: list[str], now: Optional[float] = None) -> list[str]:
        """
        Sanitize one frame of loadcell readings.

        Args:
            values: Raw readings as received from the device ("+XXXXX" style,
                or "EEEEEE"/"VVVVVV" error markers).
            now: Injectable clock for tests; defaults to time.monotonic().

        Returns:
            Sanitized readings, same length/format as input. Error markers
            pass through untouched.
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

            # Layer 1: median-of-3 kills any single-frame outlier
            # (costs one frame of latency once the window is warm).
            if not fresh:
                self._window[i] = []
            self._window[i].append(numeric)
            if len(self._window[i]) > 3:
                self._window[i].pop(0)
            if len(self._window[i]) == 3:
                value = sorted(self._window[i])[1]
            else:
                value = numeric

            # Layer 2: sign-continuity guard for glitch runs >1 frame.
            if (
                prev is not None
                and fresh
                and value * prev < 0
                and abs(value) >= cfg.min_magnitude_grams
                and abs(abs(value) - abs(prev)) <= cfg.magnitude_tolerance_grams
            ):
                self._flip_streak[i] += 1
                if self._flip_streak[i] < cfg.relatch_frames:
                    # Magnitude is trustworthy, sign is not —
                    # restore previous sign.
                    value = -value
                    self._glitch_count += 1
                    logger.debug(
                        f"Sign glitch corrected: ch={i} raw={raw} -> {value:+g} "
                        f"(total={self._glitch_count})"
                    )
                else:
                    # Inverted sign persisted: accept it as a real change.
                    self._flip_streak[i] = 0
            else:
                self._flip_streak[i] = 0

            self._prev[i] = value
            self._prev_ts[i] = ts

            quantized = self._quantize(i, value)
            if quantized == numeric:
                out.append(raw)  # untouched readings keep their original form
            else:
                out.append(self._format(quantized))

        # Channels beyond the configured count (defensive) pass through.
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
        # Hysteresis: stay in the current bin until the reading clearly
        # leaves it, so noise on a bin boundary can't flap the output
        # between adjacent bins (e.g., raw 962<->963 flapping 960<->965).
        prev_bin = self._prev_bin[ch]
        if (
            prev_bin is not None
            and abs(value - prev_bin)
            <= step / 2 + self._config.quantize_hysteresis_grams
        ):
            return prev_bin
        # Half-up rounding (Math.round semantics), symmetric with the
        # planned firmware-side implementation. round() would use
        # banker's rounding and disagree on exact half-steps.
        quantized = math.floor(value / step + 0.5) * step
        self._prev_bin[ch] = quantized
        return quantized

    @staticmethod
    def _format(value: float) -> str:
        sign = "+" if value >= 0 else "-"
        return f"{sign}{min(abs(int(value)), 99999):05d}"


# Module-level singleton, configured at application startup
# (same pattern as serial_io.configure_serial).
_sanitizer: Optional[LoadcellSanitizer] = None


def configure_sanitizer(config: SanitizeModel) -> None:
    """Configure the loadcell sanitizer. Call once during startup."""
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
    """Apply the configured sanitizer; no-op if unconfigured/disabled."""
    if _sanitizer is None:
        return values
    return _sanitizer.sanitize(values)
