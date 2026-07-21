"""loadcell 값 filter 구현 모듈.

도난 감지(anti-theft) 모니터링을 위해 loadcell 판독값을 smoothing하는
여러 filter(EMA, Kalman)를 제공한다. 에러 상태("EEEEEE", "VVVVVV")는
filter 상태에 영향을 주지 않고 그대로 전파된다.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional


# loadcell 값에 적용 가능한 filter 종류
# (docstring은 OpenAPI 스키마 description으로 노출되므로 영어 유지)
class FilterMethod(str, Enum):
    """Available filtering methods for loadcell values."""

    NONE = "none"
    EXPONENTIAL = "exponential"
    KALMAN = "kalman"


# threshold 비교 대상 — raw 값 또는 filtered 값
class ThresholdScope(str, Enum):
    """Scope for threshold comparison - raw or filtered values."""

    RAW = "raw"
    FILTERED = "filtered"


class LoadcellFilter(ABC):
    """loadcell 값 filter의 추상 base 클래스.

    filter는 lazy 초기화를 사용한다 — 첫 유효 판독값에서 상태가
    초기화된다. 에러 상태("EEEEEE", "VVVVVV")는 filter 상태에 영향
    없이 전파된다.
    """

    def __init__(self):
        """상태 없이 filter를 초기화한다."""
        self._initialized = False

    @abstractmethod
    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """loadcell 값 하나를 filtering한다.

        Args:
            value: 6자 원시 loadcell 판독값 (예: "+12345", "EEEEEE")

        Returns:
            (filtered 문자열, filtered 숫자값 또는 None) 튜플.
            에러 상태면 (원본값, None), 유효값이면 (포맷 문자열, 숫자값).
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """filter 상태를 초기화한다. IO board 재연결 시 호출된다."""
        pass

    def _parse_value(self, value: str) -> Optional[float]:
        """loadcell 문자열을 숫자값으로 파싱한다 (에러 상태면 None)."""
        if value in ("EEEEEE", "VVVVVV"):
            return None

        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _format_value(self, numeric: float) -> str:
        """숫자값을 6자 문자열로 다시 포맷한다.

        센서 resolution이 0.1이므로(소수 지원 펌웨어는 "+123.4" 같은
        판독값을 보고) 6자 필드에 들어가는 한 소수점 한 자리를
        보존한다. |값| >= 1000이면 6자에 소수점을 담을 수 없어 legacy
        정수 형식으로 fallback한다 — 소수 미지원 구형 펌웨어(정수
        판독값 최대 99999)도 그대로 동작한다.

        Args:
            numeric: loadcell 숫자값

        Returns:
            6자 포맷 문자열 (예: "+123.4", "-079.5", "+12345")
        """
        sign = "+" if numeric >= 0 else "-"
        abs_val = round(abs(numeric), 1)
        if abs_val < 1000:
            return f"{sign}{abs_val:05.1f}"
        # legacy 정수 fallback (5자리로 clamp)
        return f"{sign}{min(int(abs_val), 99999):05d}"


class NoFilter(LoadcellFilter):
    """filtering 없음 — raw 값을 그대로 통과시킨다."""

    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """raw 값을 변경 없이 반환한다."""
        numeric = self._parse_value(value)
        return (value, numeric)

    def reset(self) -> None:
        """초기화할 상태 없음."""
        pass


class ExponentialSmoothingFilter(LoadcellFilter):
    """지수 smoothing filter (EMA).

    공식: filtered = alpha * raw + (1 - alpha) * previous_filtered

    alpha 값:
    - 0.0: 최대 smoothing (느린 반응)
    - 1.0: smoothing 없음 (raw 통과)
    - 권장: loadcell 도난 감지 모니터링에는 0.1-0.3
    """

    def __init__(self, alpha: float = 0.2):
        """
        Args:
            alpha: smoothing 계수 [0.0, 1.0]. 클수록 smoothing이 약함.
        """
        super().__init__()
        self.alpha = max(0.0, min(1.0, alpha))  # [0, 1]로 clamp
        self._previous: Optional[float] = None

    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """지수 smoothing을 적용한다."""
        numeric = self._parse_value(value)

        # 에러 상태 전파
        if numeric is None:
            return (value, None)

        # 첫 유효 판독값으로 초기화
        if not self._initialized:
            self._previous = numeric
            self._initialized = True
            return (self._format_value(numeric), numeric)

        # EMA 공식 적용 (여기서 previous는 항상 non-None)
        assert self._previous is not None
        filtered = self.alpha * numeric + (1 - self.alpha) * self._previous
        self._previous = filtered

        return (self._format_value(filtered), filtered)

    def reset(self) -> None:
        """filter 상태를 초기화한다."""
        self._initialized = False
        self._previous = None


class KalmanFilter(LoadcellFilter):
    """loadcell smoothing용 단순 1D Kalman filter.

    loadcell을 Gaussian 노이즈가 섞인 정적 값으로 모델링한다.

    파라미터:
    - Q: process noise covariance (참값이 변할 수 있는 정도)
    - R: measurement noise covariance (센서 노이즈 수준)

    loadcell 권장값:
    - Q = 0.001 (무게가 천천히 변한다고 가정)
    - R = 1.0 (측정 노이즈)
    """

    def __init__(self, q: float = 0.001, r: float = 1.0):
        """
        Args:
            q: process noise covariance (Q)
            r: measurement noise covariance (R)
        """
        super().__init__()
        self.q = max(0.0001, q)  # 0/음수 방지
        self.r = max(0.0001, r)

        # 상태 변수
        self._x: Optional[float] = None  # 추정값
        self._p: float = 1.0  # 추정 오차 covariance

    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """Kalman filter를 적용한다."""
        numeric = self._parse_value(value)

        # 에러 상태 전파
        if numeric is None:
            return (value, None)

        # 첫 유효 판독값으로 초기화
        if not self._initialized:
            self._x = numeric
            self._p = 1.0
            self._initialized = True
            return (self._format_value(numeric), numeric)

        # 예측 단계 (정적 모델이므로 x_predicted = x)
        p_predicted = self._p + self.q

        # 갱신 단계: Kalman gain
        k = p_predicted / (p_predicted + self.r)

        # 추정값 갱신 (여기서 _x는 항상 non-None)
        assert self._x is not None
        self._x = self._x + k * (numeric - self._x)

        # 오차 covariance 갱신
        self._p = (1 - k) * p_predicted

        return (self._format_value(self._x), self._x)

    def reset(self) -> None:
        """filter 상태를 초기화한다."""
        self._initialized = False
        self._x = None
        self._p = 1.0


def create_filter(method: FilterMethod, **kwargs) -> LoadcellFilter:
    """filter 인스턴스를 생성하는 factory 함수.

    Args:
        method: 사용할 filter 종류
        **kwargs: filter별 파라미터 (exponential은 alpha, Kalman은 q/r)

    Returns:
        설정된 LoadcellFilter 인스턴스
    """
    if method == FilterMethod.NONE:
        return NoFilter()
    elif method == FilterMethod.EXPONENTIAL:
        alpha = kwargs.get("alpha", 0.2)
        return ExponentialSmoothingFilter(alpha=alpha)
    elif method == FilterMethod.KALMAN:
        q = kwargs.get("q", 0.001)
        r = kwargs.get("r", 1.0)
        return KalmanFilter(q=q, r=r)
    else:
        # 기본값: filtering 없음
        return NoFilter()
