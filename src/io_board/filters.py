"""
Loadcell value filtering implementations.

Provides various filtering methods for smoothing loadcell readings while
maintaining error state propagation for anti-theft monitoring.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional


class FilterMethod(str, Enum):
    """Available filtering methods for loadcell values."""
    
    NONE = "none"
    EXPONENTIAL = "exponential"
    KALMAN = "kalman"


class ThresholdScope(str, Enum):
    """Scope for threshold comparison - raw or filtered values."""
    
    RAW = "raw"
    FILTERED = "filtered"


class LoadcellFilter(ABC):
    """
    Abstract base class for loadcell value filters.
    
    Filters implement lazy initialization - state is initialized on first
    valid reading. Error states ("EEEEEE", "VVVVVV") are propagated without
    affecting filter state.
    """
    
    def __init__(self):
        """Initialize filter with no state."""
        self._initialized = False
    
    @abstractmethod
    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """
        Filter a loadcell value.
        
        Args:
            value: Raw 6-character loadcell reading (e.g., "+12345", "EEEEEE")
        
        Returns:
            Tuple of (filtered_string, filtered_numeric_or_None).
            For error states, returns (value, None).
            For valid values, returns (formatted_string, numeric_value).
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset filter state. Called when I/O board reconnects."""
        pass
    
    def _parse_value(self, value: str) -> Optional[float]:
        """
        Parse loadcell string to numeric value.
        
        Args:
            value: 6-character loadcell reading
        
        Returns:
            Numeric value or None if error state
        """
        if value in ("EEEEEE", "VVVVVV"):
            return None
        
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _format_value(self, numeric: float) -> str:
        """
        Format numeric value back to 6-character string.
        
        Args:
            numeric: Numeric loadcell value
        
        Returns:
            6-character formatted string (e.g., "+12345")
        """
        sign = "+" if numeric >= 0 else "-"
        abs_val = abs(int(numeric))
        # Clamp to 5 digits
        abs_val = min(abs_val, 99999)
        return f"{sign}{abs_val:05d}"


class NoFilter(LoadcellFilter):
    """No filtering - passes through raw values."""
    
    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """Return raw value unchanged."""
        numeric = self._parse_value(value)
        return (value, numeric)
    
    def reset(self) -> None:
        """No state to reset."""
        pass


class ExponentialSmoothingFilter(LoadcellFilter):
    """
    Exponential smoothing filter (EMA).
    
    Formula: filtered = alpha * raw + (1 - alpha) * previous_filtered
    
    Alpha values:
    - 0.0: Maximum smoothing (slow response)
    - 1.0: No smoothing (raw passthrough)
    - Typical: 0.1-0.3 for loadcell anti-theft monitoring
    """
    
    def __init__(self, alpha: float = 0.2):
        """
        Initialize exponential smoothing filter.
        
        Args:
            alpha: Smoothing factor [0.0, 1.0]. Higher = less smoothing.
        """
        super().__init__()
        self.alpha = max(0.0, min(1.0, alpha))  # Clamp to [0, 1]
        self._previous: Optional[float] = None
    
    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """Apply exponential smoothing."""
        numeric = self._parse_value(value)
        
        # Propagate error states
        if numeric is None:
            return (value, None)
        
        # Initialize on first valid reading
        if not self._initialized:
            self._previous = numeric
            self._initialized = True
            return (self._format_value(numeric), numeric)
        
        # Apply EMA formula (previous is guaranteed to be non-None here)
        assert self._previous is not None
        filtered = self.alpha * numeric + (1 - self.alpha) * self._previous
        self._previous = filtered
        
        return (self._format_value(filtered), filtered)
    
    def reset(self) -> None:
        """Reset filter state."""
        self._initialized = False
        self._previous = None


class KalmanFilter(LoadcellFilter):
    """
    Simple 1D Kalman filter for loadcell smoothing.
    
    Models loadcell as static value with Gaussian noise.
    
    Parameters:
    - Q: Process noise covariance (how much the true value can change)
    - R: Measurement noise covariance (sensor noise level)
    
    Typical values for loadcell:
    - Q = 0.001 (assumes weight changes slowly)
    - R = 1.0 (measurement noise)
    """
    
    def __init__(self, q: float = 0.001, r: float = 1.0):
        """
        Initialize Kalman filter.
        
        Args:
            q: Process noise covariance (Q)
            r: Measurement noise covariance (R)
        """
        super().__init__()
        self.q = max(0.0001, q)  # Prevent zero/negative
        self.r = max(0.0001, r)
        
        # State variables
        self._x: Optional[float] = None  # Estimated value
        self._p: float = 1.0  # Estimation error covariance
    
    def filter(self, value: str) -> tuple[str, Optional[float]]:
        """Apply Kalman filter."""
        numeric = self._parse_value(value)
        
        # Propagate error states
        if numeric is None:
            return (value, None)
        
        # Initialize on first valid reading
        if not self._initialized:
            self._x = numeric
            self._p = 1.0
            self._initialized = True
            return (self._format_value(numeric), numeric)
        
        # Prediction step
        # x_predicted = x (assumes static model)
        p_predicted = self._p + self.q
        
        # Update step
        # Kalman gain
        k = p_predicted / (p_predicted + self.r)
        
        # Update estimate (_x is guaranteed to be non-None here)
        assert self._x is not None
        self._x = self._x + k * (numeric - self._x)
        
        # Update error covariance
        self._p = (1 - k) * p_predicted
        
        return (self._format_value(self._x), self._x)
    
    def reset(self) -> None:
        """Reset filter state."""
        self._initialized = False
        self._x = None
        self._p = 1.0


def create_filter(method: FilterMethod, **kwargs) -> LoadcellFilter:
    """
    Factory function to create filter instances.
    
    Args:
        method: Filter method to use
        **kwargs: Filter-specific parameters (alpha for exponential, q/r for Kalman)
    
    Returns:
        Configured LoadcellFilter instance
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
        # Default to no filtering
        return NoFilter()
