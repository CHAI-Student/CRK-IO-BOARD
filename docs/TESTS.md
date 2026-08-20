# 테스트 구성

`tests/`는 임시 예제가 아니라 IO Board의 통신·보정·동시성 동작을 보호하는 회귀 테스트다.
전체 테스트는 하드웨어 없이 실행되며, 현재 7개 파일에 87개 항목이 있다.

## 실행

```bash
uv sync
uv run pytest
```

특정 파일만 실행하려면 다음과 같이 경로를 지정한다.

```bash
uv run pytest tests/test_serial_transaction_standalone.py -v
```

## 파일별 역할

### `test_config_standalone.py` - 23개

`core.config`의 환경 설정 모델을 검증한다.

- serial port, baudrate, timeout, retry와 inter-command gap의 기본값·범위
- API host, port, log level과 graceful shutdown timeout
- polling, sanitizer, health 설정의 기본값·validation
- `IO_BOARD__` 접두사와 `__` 중첩 환경 변수 override
- 잘못된 환경 변수 값의 초기화 실패

### `test_machine_health_deadbolt_standalone.py` - 2개

장비 상태 조회와 데드볼트 제어의 안전 조건을 검증한다.

- `/health`가 오류 이력을 지우거나 제어 명령을 보내지 않는 read-only 동작인지 확인
- 데드볼트 명령, settle 대기와 상태 재확인이 하나의 operation lock 안에서 실행되는지 확인

### `test_protocol_standalone.py` - 24개

IO Board 바이너리 프로토콜의 생성과 파싱을 검증한다.

- XOR checksum 계산과 ETX 포함 범위
- MC 초기화·데드볼트·제조번호 요청 frame
- RQ 제조정보·로드셀·IO 상태·오류 이력 응답 파싱
- checksum 불일치, STX/ETX 누락과 잘린 frame의 오류 처리
- 요청과 응답의 round-trip

### `test_sanitizer_standalone.py` - 18개

로드셀 펌웨어 이상을 보정하는 sanitizer를 검증한다.

- 단일 frame 및 채널 순회형 부호 반전 보정
- 지속된 부호 변화의 relatch와 실제 중량 변화 통과
- 영점 노이즈, 오래된 값과 오류값 처리
- median filter의 지연 특성
- 5g 양자화, half-up rounding과 경계 hysteresis

### `test_serial_transaction_standalone.py` - 7개

시리얼 응답 불일치와 동시 요청의 회귀를 검증한다.

- 직전 명령의 응답을 폐기한 뒤 재전송 없이 예상 응답 대기
- mismatch 로그의 전체 frame과 wire timing 보존
- request echo와 checksum 손상 frame 진단
- 응답 대기 중 serial transaction 소유권 유지
- timeout retry에도 RQ/IW 최소 전송 간격 적용
- complete RX 이후 inter-command gap 적용

### `test_sse_feature.py` - 9개

SSE에 사용되는 필터와 변화 감지를 검증한다.

- none, exponential, Kalman filter 생성과 계산
- 소수 로드셀 값 처리
- threshold 기반 변화 감지와 raw/filtered 기준
- `EEEEEE`, `VVVVVV` uncertainty 감지
- 단일 또는 채널별 threshold parsing

### `test_throttle_standalone.py` - 4개

로드셀 요청 속도 제한과 cache 공유를 검증한다.

- 최소 간격 이전 호출은 마지막 frame을 반환
- 간격 경과 또는 throttle 비활성화 시 새 serial 요청
- 동시 호출이 하나의 serial 요청으로 합쳐지는지 확인

## 변경 시 확인 기준

- protocol, serial transaction, sanitizer 또는 polling 변경 시 관련 파일을 먼저 실행한다.
- API·설정 변경 후에는 전체 테스트를 실행한다.
- 실제 장비 검증은 이 테스트를 대체하지 않으며, 펌웨어 문제 재현 시 관련 진단 문서와 로그를 함께 보존한다.
