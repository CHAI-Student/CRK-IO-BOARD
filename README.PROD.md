# CRK IO Board — 운영 가이드

## 사전 요구 사항

본 프로그램을 실행하기 위해서는 **uv** (astral-uv) 패키지 관리자가 시스템에 설치되어 있어야 합니다.

설치 방법은 [공식 문서](https://docs.astral.sh/uv/getting-started/installation/)를 참고하십시오.

---

## 실행 방법

프로젝트 루트 디렉터리에서 아래 명령을 실행합니다.

```bash
uv run src/main.py
```

---

## 환경 변수 설정

모든 설정값은 환경 변수를 통해 재정의할 수 있습니다.  
환경 변수는 `IO_BOARD__` 접두사를 사용하며, 중첩된 설정 항목은 `__`(이중 언더스코어)로 구분합니다.

예시:
```bash
IO_BOARD__SERIAL__PORT=/dev/ttyUSB1 IO_BOARD__API__PORT=9000 uv run src/main.py
```

또는 `.env` 파일에 설정값을 기재한 뒤 실행하는 방식도 지원됩니다.

---

### 1. 시리얼 포트 설정 (`IO_BOARD__SERIAL__*`)

IO 보드와의 시리얼 통신에 관한 설정입니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `IO_BOARD__SERIAL__PORT` | `/dev/ttyUSB0` (Linux) / `COM3` (Windows) | 연결할 시리얼 포트 경로 |
| `IO_BOARD__SERIAL__BAUDRATE` | `38400` | 통신 보레이트 (양수만 허용) |
| `IO_BOARD__SERIAL__HEADER_TIMEOUT` | `0.5` | 헤더 읽기 타임아웃 (초, 양수만 허용) |
| `IO_BOARD__SERIAL__BODY_TIMEOUT` | `2.0` | 본문 읽기 타임아웃 (초, 양수만 허용) |
| `IO_BOARD__SERIAL__CHECKSUM_TIMEOUT` | `0.5` | 체크섬 읽기 타임아웃 (초, 양수만 허용) |
| `IO_BOARD__SERIAL__MAX_RETRIES` | `3` | 명령 재시도 최대 횟수 (1 이상) |
| `IO_BOARD__SERIAL__INITIAL_RETRY_DELAY` | `0.1` | 초기 재시도 대기 시간 (초, 양수만 허용) |
| `IO_BOARD__SERIAL__RETRY_BACKOFF_MULTIPLIER` | `2.0` | 재시도 시 대기 시간 증가 배율 (1.0 이상) |

> **참고:** Linux 환경에서 시리얼 포트에 접근하려면 해당 사용자가 `dialout` 그룹에 속해 있어야 할 수 있습니다.  
> `sudo usermod -aG dialout $USER` 명령으로 추가한 후 재로그인하십시오.

---

### 2. API 서버 설정 (`IO_BOARD__API__*`)

HTTP API 서버의 바인딩 주소 및 동작에 관한 설정입니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `IO_BOARD__API__HOST` | `0.0.0.0` | 서버가 바인딩될 호스트 주소 |
| `IO_BOARD__API__PORT` | `8000` | 서버가 수신할 포트 번호 (1 ~ 65535) |
| `IO_BOARD__API__LOG_LEVEL` | `info` | 로그 출력 레벨 (아래 허용값 참조) |
| `IO_BOARD__API__TIMEOUT_GRACEFUL_SHUTDOWN` | `10` | 정상 종료 대기 시간 (초, 양수만 허용) |

**로그 레벨 허용값** (낮을수록 상세):

| 값 | 설명 |
|---|---|
| `critical` | 치명적 오류만 출력 |
| `error` | 오류 이상 출력 |
| `warning` | 경고 이상 출력 |
| `info` | 일반 정보 이상 출력 (기본값) |
| `debug` | 디버그 정보 포함 출력 |
| `trace` | 모든 내부 동작 출력 (가장 상세) |

> **운영 환경 권고:** 운영 환경에서는 `info` 또는 `warning` 레벨 사용을 권장합니다.  
> `debug` 및 `trace` 레벨은 성능에 영향을 줄 수 있으므로 문제 진단 시에만 한시적으로 사용하십시오.

---

### 3. 폴링 인터벌 설정 (`IO_BOARD__POLLING__*`)

IO 보드 상태를 주기적으로 읽어오는 폴링 서비스의 간격 설정입니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `IO_BOARD__POLLING__LOADCELLS_POLL_INTERVAL` | `0.099` | 로드셀 데이터 폴링 간격 (초, 양수만 허용) |
| `IO_BOARD__POLLING__IO_STATUS_POLL_INTERVAL` | `0.5` | IO 상태 폴링 간격 (초, 양수만 허용) |

> **참고:** 폴링 간격을 지나치게 짧게 설정하면 시리얼 통신 부하가 증가할 수 있습니다.  
> 시스템 부하 및 응답 요건을 고려하여 적절한 값으로 조정하십시오.

---

## 현재 설정값 확인

아래 명령을 실행하면 현재 적용된 모든 설정값을 JSON 형식으로 출력할 수 있습니다.

```bash
uv run src/core/config.py
```
