# API 사용법

IO Board의 REST API와 SSE 스트림을 설명한다. 현재 요청·응답 schema의 최종
기준은 실행 중인 서비스의 Swagger UI(`/docs`)와 OpenAPI JSON
(`/openapi.json`)이다.

기본 주소는 `http://localhost:8000`이며 모든 응답에 요청 추적용
`X-Correlation-ID` header가 포함된다.

## REST API

### 장비 관리

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/init` | 전원 인가 또는 reset 후 IO Board 초기화 |
| `POST` | `/calibrate` | 무부하 상태에서 전체 loadcell 보정 |
| `GET` | `/manufacturing-number` | 11자 제조번호 조회 |
| `POST` | `/manufacturing-number` | 11자 영숫자 제조번호 설정 |
| `GET` | `/software-version` | firmware version 조회 |
| `GET` | `/product-info` | 제조번호와 firmware version 조회 |
| `GET` | `/errors` | 최대 4개의 장비 오류 이력 조회 |
| `DELETE` | `/errors` | 장비 오류 이력 삭제 |
| `POST` | `/reboot` | relay를 통한 장비 재부팅 |

### 상태 조회 및 제어

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/health` | door, deadbolt와 loadcell 상태 판정 |
| `GET` | `/deadbolt` | 현재 deadbolt 상태 조회 |
| `POST` | `/deadbolt` | deadbolt 제어 후 실제 상태 재확인 |
| `GET` | `/door` | 현재 door 상태 조회 |
| `GET` | `/loadcells` | loadcell 10채널 조회 |
| `GET` | `/status` | door와 deadbolt 상태 동시 조회 |

`POST /deadbolt`의 request body는 다음과 같다.

```json
{"action": "OPEN"}
```

`action`은 `OPEN` 또는 `CLOSE`이다. 응답의 `state`는 명령 echo가 아니라
0.5초 대기 후 센서로 다시 확인한 `UNLOCK` 또는 `LOCKED` 값이다.

`GET /loadcells`는 sanitizer와 request throttle이 적용된 값을 반환한다.

```json
{
  "loadcells": [
    "+00125", "+00000", "-00010", "+00300", "+00000",
    "+00000", "+00000", "+00000", "EEEEEE", "+00000"
  ]
}
```

정상값은 부호와 숫자 5자리로 구성된 6자 문자열이다. `EEEEEE`는 통신 오류,
`VVVVVV`는 측정 범위를 벗어난 값을 뜻한다.

### 기록

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/recording/start` | 기존 기록을 비우고 메모리 기록 시작 |
| `POST` | `/recording/stop` | 기록 중지 |
| `GET` | `/recording/data` | 기록된 loadcell 값과 UTC 시각 조회 |

기록은 process memory에만 저장되므로 서비스가 재시작되면 사라진다.

## 호출 예시

```bash
curl -X POST http://localhost:8000/init
curl http://localhost:8000/loadcells
curl http://localhost:8000/status
curl -X POST http://localhost:8000/deadbolt \
  -H 'Content-Type: application/json' \
  -d '{"action":"CLOSE"}'
curl -X POST http://localhost:8000/manufacturing-number \
  -H 'Content-Type: application/json' \
  -d '{"manufacturing_number":"ABC12345678"}'
```

`/calibrate`는 선반이 비어 있을 때만 호출한다. `/reboot` 직후에는 전원이
복구될 때까지 응답 누락이 발생할 수 있다.

## SSE 스트림

통합 endpoint는 `GET /sse` 하나이다. `streams`에 `loadcells`, `doors` 또는
둘 다 지정한다.

```bash
curl -N 'http://localhost:8000/sse?streams=loadcells,doors&filter_method=exponential&filter_alpha=0.2&threshold=5&threshold_scope=filtered'
```

### Query parameter

| 이름 | 기본값 | 설명 |
|---|---:|---|
| `streams` | 필수 | `loadcells`, `doors`의 comma-separated 목록 |
| `filter_method` | `none` | `none`, `exponential`, `kalman` |
| `filter_alpha` | `0.2` | exponential smoothing 계수, `0.0`~`1.0` |
| `filter_q` | `0.001` | Kalman process noise, `0`보다 큰 값 |
| `filter_r` | `1.0` | Kalman measurement noise, `0`보다 큰 값 |
| `threshold` | `0.0` | 단일 값 또는 채널별 10개 값 |
| `threshold_scope` | `filtered` | 변화 비교 기준, `raw` 또는 `filtered` |

전송 주기는 client query로 바꾸지 않는다. loadcell과 door 주기는 각각
`IO_BOARD__POLLING__LOADCELLS_POLL_INTERVAL`,
`IO_BOARD__POLLING__IO_STATUS_POLL_INTERVAL` 설정을 따른다.

### Event

SSE wire format은 다음과 같다.

```text
event: loadcell.update
data: {"timestamp":"...Z","raw_values":[...],"filtered_values":[...],"filter_method":"none"}

```

| Event | 발생 조건 | 주요 data |
|---|---|---|
| `loadcell.update` | loadcell poll 성공 시 항상 | `raw_values`, `filtered_values`, `filter_method` |
| `loadcell.change` | 설정한 threshold 초과 시 | `changed_indices`, `old_values`, `new_values`, `deltas` |
| `loadcell.uncertainty` | 오류값 또는 IO Board 장애 감지 시 | `affected_indices`, `reason`, `details` |
| `door.update` | IO status poll 성공 시 | `door`, `deadbolt` |
| `error` | stream 처리 오류 시 | `stream`, `error_code`, `message`, `details` |

장비 통신 오류가 발생해도 SSE 연결은 유지된다. loadcell 통신 오류에서는
filter를 reset하고 전체 채널에 `loadcell.uncertainty`와 `error`를 함께 보낸다.
door 통신 오류에서는 `error`만 보낸다. client disconnect 또는 server
shutdown 시 구독과 background task를 정리한다.

### Threshold 선택

- `raw`: 필터 이전 센서 변화에 빠르게 반응한다.
- `filtered`: 노이즈에 덜 민감하지만 필터만큼 반응이 늦을 수 있다.
- 단일 threshold는 10채널 전체에 적용된다.
- 채널별 threshold는 comma-separated 숫자 10개를 전달한다.

```bash
curl -N 'http://localhost:8000/sse?streams=loadcells&threshold=5,5,10,10,5,5,10,10,5,5&threshold_scope=raw'
```

## 오류 응답

REST 오류는 다음 형태를 사용한다.

```json
{
  "error_code": "E2001",
  "message": "Serial communication failed",
  "details": {}
}
```

- request validation 오류는 HTTP `422`를 사용한다.
- 장비·protocol·serial 오류는 HTTP `500`과 해당 error code를 반환한다.
- 예상하지 못한 server 오류는 `E9001`을 반환한다.
- SSE의 잘못된 `streams` 또는 `threshold`는 `E4002`~`E4006`을 반환한다.
- 연결 이후 발생한 SSE 오류는 HTTP 응답을 바꾸지 않고 `error` event로 전달한다.

장비 binary protocol과 device error code는 [PROTOCOL.md](PROTOCOL.md)를
참고한다.
