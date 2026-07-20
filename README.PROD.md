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
| `IO_BOARD__POLLING__LOADCELLS_POLL_INTERVAL` | `0.8` | 로드셀 데이터 폴링 간격 (초, 양수만 허용). `LOADCELLS_MIN_REQUEST_GAP`보다 커야 recording이 캐시가 아닌 신선한 프레임을 받습니다 |
| `IO_BOARD__POLLING__IO_STATUS_POLL_INTERVAL` | `0.5` | IO 상태 폴링 간격 (초, 양수만 허용) |
| `IO_BOARD__POLLING__LOADCELLS_MIN_REQUEST_GAP` | `0.75` | 로드셀 시리얼 요청 최소 간격 (초). 이보다 빠른 호출은 캐시로 응답. `0`이면 비활성 |

> **경고:** 펌웨어가 로드셀 요청 간격 ~0.7초 미만에서 **부호를 잘못 보고**합니다
> (실측 duty: 0.09s→0.89, 0.5s→0.25, 0.6s→0.03, 0.7s→0.00 —
> `docs/FIRMWARE_SIGN_GLITCH_REQUEST.md` 참조). `LOADCELLS_MIN_REQUEST_GAP`을
> 0.7 미만으로 낮추거나 끄면 부호 손상이 재발합니다. 기존 배포에서
> `LOADCELLS_POLL_INTERVAL`을 0.12 등으로 명시 설정했다면 **env 오버라이드를
> 제거하거나 0.8 이상으로 변경**해야 합니다.

---

### 4. 로드셀 새니타이저 설정 (`IO_BOARD__SANITIZE__*`)

펌웨어 부호 글리치(크기 보존·1프레임 부호 반전, issue #1) 보정과
센서 보증 분해능(5g) 양자화 설정입니다. `get_loadcells()` 관문에 적용되어
`/loadcells`, SSE, `/recording/data` 모두 동일하게 반영됩니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `IO_BOARD__SANITIZE__ENABLED` | `true` | 부호 글리치 보정 활성화 |
| `IO_BOARD__SANITIZE__MAGNITUDE_TOLERANCE_GRAMS` | `2.0` | 부호 반전을 글리치로 볼 크기 차 허용오차 (g) |
| `IO_BOARD__SANITIZE__MIN_MAGNITUDE_GRAMS` | `5.0` | 이 크기 미만은 보정하지 않음 (영점 노이즈 보호) |
| `IO_BOARD__SANITIZE__RELATCH_FRAMES` | `3` | 반전 부호가 이 프레임 수 연속되면 진짜 변화로 수용 |
| `IO_BOARD__SANITIZE__STALENESS_SECONDS` | `2.0` | 이보다 오래된 직전 값은 글리치 판정에 사용 안 함 |
| `IO_BOARD__SANITIZE__QUANTIZE_GRAMS` | `5.0` | 출력 양자화 스텝 (g, `0`이면 비활성) |
| `IO_BOARD__SANITIZE__QUANTIZE_HYSTERESIS_GRAMS` | `1.0` | 양자화 bin 이탈에 필요한 추가 마진 (경계 플래핑 억제) |

> **참고:** 미디언-of-3 1차 방어로 인해 출력이 원시 대비 1프레임(폴링 간격 1회)
> 지연됩니다. 양자화는 값이 bin 경계에 걸릴 때 가짜 5g 스텝을 만들 수 있으므로,
> 추론 delta 정밀도가 우선이면 `QUANTIZE_GRAMS=0`으로 끄고 판정 계층에서
> 양자화하는 구성도 고려하십시오.

---

## 현재 설정값 확인

아래 명령을 실행하면 현재 적용된 모든 설정값을 JSON 형식으로 출력할 수 있습니다.

```bash
uv run src/core/config.py
```
