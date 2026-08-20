# 서비스 구조

IO Board 서비스는 FastAPI 요청을 고수준 command로 변환하고, binary protocol과
단일 serial 연결을 통해 장비와 통신한다. SSE와 기록은 공통 polling 결과를
구독해 불필요한 중복 요청을 줄인다.

## 구성

```text
Client
  ├─ REST ───────────────> API router ─────────────> IO Board commands
  └─ SSE / Recording ────> Polling subscriber ─────> IO Board commands
                                                    │
                     Filter / Event detector <──────┤
                                                    v
                                  Sanitizer → Protocol → Serial → Device
```

| 영역 | 경로 | 책임 |
|---|---|---|
| 진입점 | `src/main.py` | 설정, lifespan, middleware, router, graceful shutdown |
| API | `src/api/v1/routers/` | management, machine, recording, SSE endpoint |
| 설정·로그 | `src/core/` | 환경변수 검증, 구조화 로그, UTC 변환 |
| command | `src/services/io_board/commands.py` | 장비 동작 단위와 loadcell throttle |
| protocol | `src/services/io_board/protocol.py` | frame 생성, checksum 및 응답 parsing |
| serial | `src/services/io_board/serial_io.py` | 연결 재사용, mutex, timeout, retry와 응답 matching |
| 보정 | `src/services/io_board/sanitizer.py` | 부호 글리치 보정과 5g 양자화 |
| polling | `src/services/polling/` | loadcell·IO status 수집과 subscriber broadcast |
| SSE 처리 | `src/io_board/filters.py`, `events.py` | EMA/Kalman filter, threshold와 uncertainty 감지 |
| 기록·health 상태 | `src/services/recording.py`, `error_state_mgmt.py` | 메모리 기록, door/deadbolt 상태 추적 |

## 시작과 종료

`src/main.py`의 lifespan은 다음 순서로 서비스를 구성한다.

1. 설정을 읽고 logging, serial, sanitizer와 loadcell throttle을 구성한다.
2. loadcell과 IO status polling service를 시작한다.
3. recording service와 health용 error-state service를 시작한다.
4. 종료 시 recording subscriber를 먼저 정리하고 polling service를 중지한다.
5. uvicorn shutdown 시 공유 stop event를 설정해 SSE generator를 종료한다.

PollingService는 subscriber가 있을 때만 장비를 polling한다. IO status는 health
상태 추적 service가 상시 구독한다. loadcell은 SSE 또는 recording이 구독할
때 활성화되며, 일반 REST 조회는 command를 직접 호출한다.

## REST 데이터 흐름

```text
HTTP request
  → correlation ID middleware
  → router validation
  → commands
  → protocol.build_request
  → serial.fetch
  → protocol.parse_response
  → response model
```

Serial layer는 하나의 mutex로 transaction 전체를 보호한다. timing gate가 끝난
실제 TX 직전에 stale input을 비운다. 관련 없는 CMD/SUBCMD 응답은 폐기하고
exponential backoff 후 동일 요청을 다시 전송하며, 설정된 횟수만큼 반복해도
일치하지 않으면 protocol 오류로 처리한다. 완전한 RX 이후 inter-command gap과
동일 request의 최소 TX 간격도 적용한다.

Loadcell 조회에는 모든 caller가 공유하는 gate가 있다. 설정된 최소 간격보다
빠른 호출은 마지막 sanitize 결과를 반환한다. 새 frame에는 부호 글리치 보정과
설정된 양자화가 적용되므로 REST, SSE와 recording이 같은 값을 사용한다.

## SSE 및 기록 흐름

```text
PollingService
  ├─ SSE StreamQueue → filter → change detector → SSE event
  ├─ Recording StreamQueue → in-memory log
  └─ ErrorState StreamQueue → door/deadbolt health state
```

각 subscriber는 독립된 `StreamQueue`를 가진다. polling 성공 결과는 data와
timestamp로 전달되고, 실패 결과는 queue 소비 시 원래 예외로 다시 발생한다.

SSE client별 filter와 threshold 상태는 서로 공유하지 않는다. loadcell과 door를
동시에 요청하면 두 polling queue에서 받은 event를 하나의 SSE queue로
multiplexing한다. 자세한 event 규격은 [API.md](API.md)를 참고한다.

Recording은 loadcell polling을 구독해 process memory에 저장한다. 영속 저장소는
사용하지 않는다.

## Health 판정

`GET /health`는 상태를 변경하지 않는 read-only probe이다.

- loadcell: 10개 값의 형식과 설정된 정상 범위를 확인한다.
- door: 마지막 닫힘 이후 열린 상태가 허용 시간을 넘었는지 확인한다.
- deadbolt: 최근 제어 목표가 제한 시간 안에 반영됐는지와 현재 IO 상태를 확인한다.

과거 장비 오류 FIFO를 지우거나 초기화·제어 명령을 보내지 않는다. deadbolt
제어는 command 전송부터 0.5초 settle 및 상태 재확인까지 별도 operation lock으로
직렬화한다.

## 오류와 관측

모든 HTTP request에 correlation ID가 부여되며 응답의
`X-Correlation-ID`에도 포함된다. 장비 관련 예외는 표준 error response로
변환한다. serial DEBUG 로그에는 TX/RX hex, transaction과 응답 mismatch 진단이
남는다.

Protocol 상세는 [PROTOCOL.md](PROTOCOL.md), 운영 절차는
[OPERATIONS.md](OPERATIONS.md)를 참고한다.
