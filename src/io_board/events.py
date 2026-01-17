"""
Loadcell event detection for threshold-based change monitoring.

Detects significant changes in loadcell values and generates events for
anti-theft monitoring. Any uncertainty (errors, parse failures, I/O failures)
is treated as a potential theft event.
"""

from datetime import datetime
from typing import Optional

from .filters import LoadcellFilter, ThresholdScope, create_filter, FilterMethod


class LoadcellChangeDetector:
    """
    Detects threshold-based changes in loadcell values.
    
    Manages per-loadcell filtering and tracks previous values to detect
    significant changes. Generates uncertainty events for any error conditions.
    """
    
    def __init__(
        self,
        filter_method: FilterMethod = FilterMethod.NONE,
        thresholds: Optional[list[float]] = None,
        threshold_scope: ThresholdScope = ThresholdScope.FILTERED,
        **filter_kwargs
    ):
        """
        Initialize change detector.
        
        Args:
            filter_method: Filtering method to apply
            thresholds: List of 10 threshold values (one per loadcell)
            threshold_scope: Apply thresholds to raw or filtered values
            **filter_kwargs: Filter-specific parameters (alpha, q, r, etc.)
        """
        self.filter_method = filter_method
        self.threshold_scope = threshold_scope
        
        # Create 10 filters (one per loadcell)
        self.filters: list[LoadcellFilter] = [
            create_filter(filter_method, **filter_kwargs)
            for _ in range(10)
        ]
        
        # Store thresholds (default to 0.0 if not provided)
        if thresholds is None:
            self.thresholds = [0.0] * 10
        else:
            self.thresholds = thresholds
        
        # Track previous values for change detection
        self._previous_raw: list[Optional[float]] = [None] * 10
        self._previous_filtered: list[Optional[float]] = [None] * 10
    
    def process(
        self, 
        raw_values: list[str]
    ) -> tuple[list[str], list[Optional[float]], list[int], dict]:
        """
        Process loadcell readings and detect changes.
        
        Args:
            raw_values: List of 10 raw loadcell strings
        
        Returns:
            Tuple of:
            - filtered_strings: List of 10 filtered loadcell strings
            - filtered_numerics: List of 10 filtered numeric values (or None)
            - changed_indices: Indices of loadcells that exceeded threshold
            - change_details: Dict with old/new values and deltas for changed loadcells
        """
        if len(raw_values) != 10:
            raise ValueError(f"Expected 10 loadcell values, got {len(raw_values)}")
        
        filtered_strings = []
        filtered_numerics = []
        changed_indices = []
        change_details = {
            "old_values": [],
            "new_values": [],
            "deltas": []
        }
        
        # Process each loadcell
        for i in range(10):
            raw_str = raw_values[i]
            
            # Apply filter
            filtered_str, filtered_num = self.filters[i].filter(raw_str)
            filtered_strings.append(filtered_str)
            filtered_numerics.append(filtered_num)
            
            # Parse raw value for raw scope comparison
            raw_num = self._parse_value(raw_str)
            
            # Determine which value to use for threshold comparison
            if self.threshold_scope == ThresholdScope.RAW:
                compare_value = raw_num
                previous_value = self._previous_raw[i]
            else:  # FILTERED
                compare_value = filtered_num
                previous_value = self._previous_filtered[i]
            
            # Check for threshold breach
            if compare_value is not None and previous_value is not None:
                delta = abs(compare_value - previous_value)
                if delta > self.thresholds[i]:
                    changed_indices.append(i)
                    change_details["old_values"].append(previous_value)
                    change_details["new_values"].append(compare_value)
                    change_details["deltas"].append(delta)
            
            # Update previous values
            self._previous_raw[i] = raw_num
            self._previous_filtered[i] = filtered_num
        
        return filtered_strings, filtered_numerics, changed_indices, change_details
    
    def detect_uncertainties(
        self, 
        raw_values: list[str],
        filtered_numerics: list[Optional[float]]
    ) -> list[int]:
        """
        Detect loadcells with uncertainty (error states).
        
        Args:
            raw_values: List of 10 raw loadcell strings
            filtered_numerics: List of 10 filtered numeric values
        
        Returns:
            List of indices with uncertainty (None values or error strings)
        """
        uncertain_indices = []
        
        for i in range(10):
            # Check for error strings
            if raw_values[i] in ("EEEEEE", "VVVVVV"):
                uncertain_indices.append(i)
            # Check for parse failures
            elif filtered_numerics[i] is None:
                uncertain_indices.append(i)
        
        return uncertain_indices
    
    def reset(self) -> None:
        """
        Reset all filter states and previous values.
        
        Called when I/O board reconnects to clear stale state.
        """
        for filter_obj in self.filters:
            filter_obj.reset()
        
        self._previous_raw = [None] * 10
        self._previous_filtered = [None] * 10
    
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
