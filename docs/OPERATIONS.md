# 운영 및 장애 대응

IO Board 서비스의 실행, 확인과 장애 대응 절차를 정리한다. 전체 환경변수와
기본값은 [README.PROD.md](../README.PROD.md)를 기준으로 한다.

## 실행

```bash
uv sync
uv run src/main.py
```

기본 bind 주소는 `0.0.0.0:8000`이다. 실행 후 다음 주소를 확인한다.

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Health: `http://localhost:8000/health`

설정은 `IO_BOARD__` prefix와 `__` 중첩 구분자를 사용한다.

```bash
export IO_BOARD__SERIAL__PORT=/dev/ttyUSB0
export IO_BOARD__API__LOG_LEVEL=debug
uv run src/main.py
```

현재 적용될 설정은 장비 연결 없이 출력할 수 있다.

```bash
uv run src/core/config.py
```

## 운영 전 확인

```bash
curl http://localhost:8000/product-info
curl http://localhost:8000/status
curl http://localhost:8000/loadcells
curl http://localhost:8000/health
curl http://localhost:8000/errors
```

- `/product-info`: serial 연결과 제조정보 응답을 확인한다.
- `/status`: door와 deadbolt 센서 상태를 확인한다.
- `/loadcells`: 10개 값이 있고 `EEEEEE`, `VVVVVV`가 없는지 확인한다.
- `/health`: 세 항목이 모두 `HEALTHY`인지 확인한다.
- `/errors`: `0000` 이외의 device error code가 있는지 확인한다.

`/health`는 장비 오류 이력을 삭제하지 않고 제어 명령도 보내지 않는다.
오류 이력 삭제는 확인 후 `DELETE /errors`로 명시적으로 수행한다.

## 로그

로그 형식은 다음과 같다.

```text
[timestamp] [LEVEL] [correlation_id] [logger] message
```

HTTP 응답의 `X-Correlation-ID`를 이용하면 한 요청의 API, command와 serial
로그를 연결해 찾을 수 있다. `debug` level에서는 다음 정보가 추가된다.

- serial TX/RX 전체 frame의 hex와 byte 길이
- command 및 serial transaction 소요 시간
- 기대하지 않은 CMD/SUBCMD frame과 wire timing
- throttle cache 사용과 sanitizer 보정

요청 body가 DEBUG로 기록될 수 있으므로 제조번호 외에 민감한 값을 endpoint에
추가할 경우 logging policy를 먼저 검토한다.

## Serial 장애 대응

1. `IO_BOARD__SERIAL__PORT`와 OS의 실제 장치 경로를 확인한다.
2. baudrate가 `38400`인지 확인한다.
3. log level을 `debug`로 올리고 동일 요청을 재현한다.
4. TX/RX hex, transaction ID, CMD/SUBCMD와 timing 로그를 보존한다.
5. `GET /product-info`, `/status`, `/loadcells`을 순서대로 호출해 명령별 차이를 확인한다.

Serial port는 요청마다 열지 않고 재사용하며 transaction은 mutex로 직렬화된다.
Timeout은 header, body와 checksum 단계로 나뉘고 실패 시 exponential backoff로
재시도한다. 모든 재시도 후 실패하면 `E2xxx` 계열 오류를 반환한다.

`Unexpected response CMD/SUBCMD`는 정상적인 noise로 간주하지 않는다. 관련 없는
frame은 폐기하고 exponential backoff 후 동일 요청을 재전송한다. 반복되면
[KNOWN_RESPONSE_MISMATCH.md](KNOWN_RESPONSE_MISMATCH.md)에 따라 원본 frame과
timing을 수집한다.

## Loadcell 이상 대응

- 정상 형식: `+XXXXX` 또는 `-XXXXX`
- 통신 오류: `EEEEEE`
- 범위 오류: `VVVVVV`
- 기본 health 정상 범위: `-40000g`~`40000g`

RQIW 요청을 너무 빠르게 전송하면 firmware 부호 손상이 재현되므로 기본
loadcell polling 주기 `0.8s`와 최소 요청 간격 `0.75s`를 임의로 낮추지 않는다.
빠른 HTTP 호출은 같은 gate의 cache를 사용하며 timeout retry에도 wire 최소
간격이 적용된다.

부호 반전이나 영점 이동이 관측되면 다음 문서와 함께 raw DEBUG 로그를 보존한다.

- [부호 글리치 펌웨어 요청](FIRMWARE_SIGN_GLITCH_REQUEST.md)
- [zero-tracking 펌웨어 요청](FIRMWARE_ZERO_TRACKING_REQUEST.md)

Sanitizer는 host-side 완화책이며 firmware 원인 해결을 대체하지 않는다.

## SSE 운영

```bash
curl -N 'http://localhost:8000/sse?streams=loadcells,doors'
```

SSE 전송 주기는 client별 query가 아니라 전역 polling 설정을 따른다. 연결이
끊기면 해당 subscriber와 background task가 정리되며 다른 client에는 영향을
주지 않는다. 장비 통신 오류는 `error` event로 전달되고 연결은 유지된다.

Event format과 filter·threshold 사용법은 [API.md](API.md)를 참고한다.

## 기록 운영

`POST /recording/start`는 기존 메모리 기록을 비우고 새 기록을 시작한다.
`POST /recording/stop`은 기록을 멈추며 `GET /recording/data`로 조회할 수 있다.

기록은 file이나 database에 저장되지 않는다. 장시간 기록은 memory 사용량을
계속 늘리며 process 재시작 시 모두 사라지므로 진단에 필요한 데이터는 외부로
내보낸 뒤 재시작한다.

## 안전한 제어

- `/calibrate`는 모든 선반이 비어 있을 때만 호출한다.
- `/reboot` 동안 장비 응답이 일시적으로 사라질 수 있다.
- deadbolt 제어 응답은 명령 전송 후 실제 sensor 상태를 재확인한 결과다.
- `/errors` 삭제 전 오류 코드를 기록한다.
- 설정 변경 후에는 [TESTS.md](TESTS.md)의 전체 회귀 테스트를 실행한다.

## 종료

서비스 종료 시 SSE stop event를 설정하고 recording, error-state와 polling
service를 순서대로 정리한다. 설정된 graceful shutdown timeout 안에 종료되지
않으면 진행 중인 serial 또는 streaming 작업의 로그를 확인한다.
