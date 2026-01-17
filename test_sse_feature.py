"""
Basic tests for the new SSE streaming feature.

Run with: python test_sse_feature.py
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from io_board.filters import (
    FilterMethod,
    ThresholdScope,
    NoFilter,
    ExponentialSmoothingFilter,
    KalmanFilter,
    create_filter,
)
from io_board.events import LoadcellChangeDetector


def test_filter_creation():
    """Test filter factory function."""
    print("Testing filter creation...")
    
    # Test NoFilter
    f1 = create_filter(FilterMethod.NONE)
    assert isinstance(f1, NoFilter), "Failed to create NoFilter"
    
    # Test ExponentialSmoothingFilter
    f2 = create_filter(FilterMethod.EXPONENTIAL, alpha=0.3)
    assert isinstance(f2, ExponentialSmoothingFilter), "Failed to create ExponentialSmoothingFilter"
    
    # Test KalmanFilter
    f3 = create_filter(FilterMethod.KALMAN, q=0.01, r=2.0)
    assert isinstance(f3, KalmanFilter), "Failed to create KalmanFilter"
    
    print("✓ Filter creation tests passed")


def test_no_filter():
    """Test NoFilter passes through values."""
    print("Testing NoFilter...")
    
    f = NoFilter()
    
    # Test normal value
    result, numeric = f.filter("+12345")
    assert result == "+12345", f"Expected '+12345', got '{result}'"
    assert numeric == 12345.0, f"Expected 12345.0, got {numeric}"
    
    # Test error value
    result, numeric = f.filter("EEEEEE")
    assert result == "EEEEEE", f"Expected 'EEEEEE', got '{result}'"
    assert numeric is None, f"Expected None, got {numeric}"
    
    print("✓ NoFilter tests passed")


def test_exponential_filter():
    """Test exponential smoothing filter."""
    print("Testing ExponentialSmoothingFilter...")
    
    f = ExponentialSmoothingFilter(alpha=0.5)
    
    # First value initializes
    result1, numeric1 = f.filter("+10000")
    assert numeric1 == 10000.0, f"First value should be 10000.0, got {numeric1}"
    
    # Second value applies smoothing
    result2, numeric2 = f.filter("+20000")
    expected = 0.5 * 20000 + 0.5 * 10000  # = 15000
    assert numeric2 == expected, f"Expected {expected}, got {numeric2}"
    
    # Error value doesn't affect state
    result3, numeric3 = f.filter("EEEEEE")
    assert numeric3 is None, "Error should return None"
    
    # Next valid value continues from previous state
    result4, numeric4 = f.filter("+20000")
    expected = 0.5 * 20000 + 0.5 * 15000  # = 17500
    assert numeric4 == expected, f"Expected {expected}, got {numeric4}"
    
    # Test reset
    f.reset()
    result5, numeric5 = f.filter("+10000")
    assert numeric5 == 10000.0, f"After reset, should reinitialize to 10000.0, got {numeric5}"
    
    print("✓ ExponentialSmoothingFilter tests passed")


def test_kalman_filter():
    """Test Kalman filter."""
    print("Testing KalmanFilter...")
    
    f = KalmanFilter(q=0.001, r=1.0)
    
    # First value initializes
    result1, numeric1 = f.filter("+10000")
    assert numeric1 == 10000.0, f"First value should be 10000.0, got {numeric1}"
    
    # Second value applies Kalman update
    result2, numeric2 = f.filter("+10100")
    assert numeric2 is not None, "Second value should not be None"
    assert 10000 < numeric2 < 10100, f"Filtered value should be between 10000 and 10100, got {numeric2}"
    
    # Test reset
    f.reset()
    result3, numeric3 = f.filter("+10000")
    assert numeric3 == 10000.0, f"After reset, should reinitialize to 10000.0, got {numeric3}"
    
    print("✓ KalmanFilter tests passed")


def test_change_detector_basic():
    """Test basic change detection."""
    print("Testing LoadcellChangeDetector...")
    
    detector = LoadcellChangeDetector(
        filter_method=FilterMethod.NONE,
        thresholds=[10.0] * 10,
        threshold_scope=ThresholdScope.RAW
    )
    
    # First reading initializes
    raw1 = ["+10000"] * 10
    filtered, numerics, changed, details = detector.process(raw1)
    assert len(changed) == 0, "First reading should not trigger changes"
    
    # Small change (below threshold)
    raw2 = ["+10005"] * 10
    filtered, numerics, changed, details = detector.process(raw2)
    assert len(changed) == 0, "Change of 5 should not exceed threshold of 10"
    
    # Large change (above threshold)
    raw3 = ["+10020"] * 10
    filtered, numerics, changed, details = detector.process(raw3)
    assert len(changed) == 10, f"All loadcells should change, got {len(changed)} changes"
    assert all(d > 10.0 for d in details["deltas"]), "All deltas should exceed 10.0"
    
    print("✓ LoadcellChangeDetector basic tests passed")


def test_uncertainty_detection():
    """Test uncertainty detection."""
    print("Testing uncertainty detection...")
    
    detector = LoadcellChangeDetector(
        filter_method=FilterMethod.NONE,
        thresholds=[10.0] * 10,
        threshold_scope=ThresholdScope.RAW
    )
    
    # Normal values
    raw1 = ["+10000"] * 10
    filtered, numerics, changed, details = detector.process(raw1)
    uncertain = detector.detect_uncertainties(raw1, numerics)
    assert len(uncertain) == 0, "No uncertainties expected for normal values"
    
    # Values with errors
    raw2 = ["+10000"] * 5 + ["EEEEEE"] * 3 + ["VVVVVV"] * 2
    filtered, numerics, changed, details = detector.process(raw2)
    uncertain = detector.detect_uncertainties(raw2, numerics)
    assert len(uncertain) == 5, f"Expected 5 uncertain loadcells, got {len(uncertain)}"
    assert set(uncertain) == {5, 6, 7, 8, 9}, f"Expected indices 5-9, got {uncertain}"
    
    print("✓ Uncertainty detection tests passed")


def test_filtered_threshold_scope():
    """Test threshold applied to filtered values."""
    print("Testing filtered threshold scope...")
    
    # Use strong smoothing to demonstrate filtered scope
    detector = LoadcellChangeDetector(
        filter_method=FilterMethod.EXPONENTIAL,
        thresholds=[10.0] * 10,
        threshold_scope=ThresholdScope.FILTERED,
        alpha=0.1  # Heavy smoothing
    )
    
    # Initialize
    raw1 = ["+10000"] * 10
    detector.process(raw1)
    
    # Large raw change, but smoothing keeps filtered change small
    raw2 = ["+10050"] * 10  # Raw delta = 50
    filtered, numerics, changed, details = detector.process(raw2)
    
    # With alpha=0.1, filtered = 0.1*10050 + 0.9*10000 = 10005
    # Filtered delta = 5, which is < threshold of 10
    assert len(changed) == 0, f"Filtered change should not exceed threshold, but got {len(changed)} changes"
    
    print("✓ Filtered threshold scope tests passed")


def test_threshold_parsing():
    """Test threshold parameter parsing logic."""
    print("Testing threshold parsing...")
    
    # Single value broadcast
    thresholds_single = [5.0] * 10
    detector1 = LoadcellChangeDetector(thresholds=thresholds_single)
    assert detector1.thresholds == [5.0] * 10, "Single value should broadcast to all 10"
    
    # Per-loadcell values
    thresholds_list = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    detector2 = LoadcellChangeDetector(thresholds=thresholds_list)
    assert detector2.thresholds == thresholds_list, "Per-loadcell thresholds should be preserved"
    
    print("✓ Threshold parsing tests passed")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("Running SSE Feature Tests")
    print("="*60 + "\n")
    
    try:
        test_filter_creation()
        test_no_filter()
        test_exponential_filter()
        test_kalman_filter()
        test_change_detector_basic()
        test_uncertainty_detection()
        test_filtered_threshold_scope()
        test_threshold_parsing()
        
        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60 + "\n")
        return 0
    
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}\n")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
