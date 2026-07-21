"""시간 변환 공용 유틸리티.

sse.py와 recording router에서 중복 정의되던 unix_to_iso8601()을
한 곳으로 모은 모듈. 출력 포맷(UTC, Z suffix)은 기존과 동일하다.
"""

from datetime import datetime, timezone


def unix_to_iso8601(timestamp: float) -> str:
    """UNIX timestamp를 ISO 8601(UTC, Z suffix) 형식으로 변환한다."""
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
