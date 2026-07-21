"""threshold 기반 loadcell 변화 감지 모듈.

loadcell 값의 유의미한 변화를 감지해 도난 감지(anti-theft) 모니터링용
이벤트를 생성한다. 모든 불확실성(에러 상태, 파싱 실패, IO board 장애)은
잠재적 도난 이벤트로 취급한다.
"""

from typing import Optional

from .filters import LoadcellFilter, ThresholdScope, create_filter, FilterMethod


class LoadcellChangeDetector:
    """threshold 기반 loadcell 값 변화 감지기.

    loadcell별 filtering을 관리하고 직전 값을 추적해 유의미한 변화를
    감지한다. 에러 조건에 대해서는 uncertainty 이벤트를 생성한다.
    """

    def __init__(
        self,
        filter_method: FilterMethod = FilterMethod.NONE,
        thresholds: Optional[list[float]] = None,
        threshold_scope: ThresholdScope = ThresholdScope.FILTERED,
        **filter_kwargs
    ):
        """
        Args:
            filter_method: 적용할 filter 종류
            thresholds: threshold 값 10개 리스트 (loadcell당 1개)
            threshold_scope: threshold를 raw/filtered 중 어느 값에 적용할지
            **filter_kwargs: filter별 파라미터 (alpha, q, r 등)
        """
        self.filter_method = filter_method
        self.threshold_scope = threshold_scope

        # filter 10개 생성 (loadcell당 1개)
        self.filters: list[LoadcellFilter] = [
            create_filter(filter_method, **filter_kwargs)
            for _ in range(10)
        ]

        # threshold 저장 (미지정 시 0.0)
        if thresholds is None:
            self.thresholds = [0.0] * 10
        else:
            self.thresholds = thresholds

        # 변화 감지를 위한 직전 값 추적
        self._previous_raw: list[Optional[float]] = [None] * 10
        self._previous_filtered: list[Optional[float]] = [None] * 10

    def process(
        self,
        raw_values: list[str]
    ) -> tuple[list[str], list[Optional[float]], list[int], dict]:
        """loadcell 판독값을 처리하고 변화를 감지한다.

        Args:
            raw_values: 원시 loadcell 문자열 10개 리스트

        Returns:
            다음 요소의 튜플:
            - filtered_strings: filtered loadcell 문자열 10개
            - filtered_numerics: filtered 숫자값 10개 (또는 None)
            - changed_indices: threshold를 초과한 loadcell 인덱스
            - change_details: 변화한 loadcell의 old/new 값과 delta 딕셔너리
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
        
        # loadcell별 처리
        for i in range(10):
            raw_str = raw_values[i]

            # filter 적용
            filtered_str, filtered_num = self.filters[i].filter(raw_str)
            filtered_strings.append(filtered_str)
            filtered_numerics.append(filtered_num)

            # raw scope 비교를 위해 raw 값 파싱
            raw_num = self._parse_value(raw_str)

            # threshold 비교에 사용할 값 선택 (raw vs filtered)
            if self.threshold_scope == ThresholdScope.RAW:
                compare_value = raw_num
                previous_value = self._previous_raw[i]
            else:  # FILTERED
                compare_value = filtered_num
                previous_value = self._previous_filtered[i]

            # threshold 초과 검사
            if compare_value is not None and previous_value is not None:
                delta = abs(compare_value - previous_value)
                if delta > self.thresholds[i]:
                    changed_indices.append(i)
                    # 센서 resolution(0.1)로 반올림 — 이벤트 payload에
                    # float 잔재가 남지 않도록. 위의 비교 자체는 전체
                    # float로 수행된다.
                    change_details["old_values"].append(round(previous_value, 1))
                    change_details["new_values"].append(round(compare_value, 1))
                    change_details["deltas"].append(round(delta, 1))

            # 직전 값 갱신
            self._previous_raw[i] = raw_num
            self._previous_filtered[i] = filtered_num

        return filtered_strings, filtered_numerics, changed_indices, change_details

    def detect_uncertainties(
        self,
        raw_values: list[str],
        filtered_numerics: list[Optional[float]]
    ) -> list[int]:
        """불확실성(에러 상태)이 있는 loadcell을 감지한다.

        Args:
            raw_values: 원시 loadcell 문자열 10개 리스트
            filtered_numerics: filtered 숫자값 10개 리스트

        Returns:
            불확실성이 있는 인덱스 리스트 (None 값 또는 에러 문자열)
        """
        uncertain_indices = []

        for i in range(10):
            # 에러 문자열 검사
            if raw_values[i] in ("EEEEEE", "VVVVVV"):
                uncertain_indices.append(i)
            # 파싱 실패 검사
            elif filtered_numerics[i] is None:
                uncertain_indices.append(i)

        return uncertain_indices

    def reset(self) -> None:
        """모든 filter 상태와 직전 값을 초기화한다.

        IO board 재연결 시 stale 상태를 제거하기 위해 호출된다.
        """
        for filter_obj in self.filters:
            filter_obj.reset()

        self._previous_raw = [None] * 10
        self._previous_filtered = [None] * 10

    def _parse_value(self, value: str) -> Optional[float]:
        """loadcell 문자열을 숫자값으로 파싱한다 (에러 상태면 None)."""
        if value in ("EEEEEE", "VVVVVV"):
            return None
        
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
