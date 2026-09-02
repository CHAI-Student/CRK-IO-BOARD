# IO Board Issue Handoff

이 문서는 CRK IO Board API에서 확인된 통신, deadbolt, loadcell 처리 이슈와
현재 적용된 호스트 측 완화책을 설명한다. 보드 펌웨어를 수정할 수 없는 상황을
전제로 하며, 처음 보는 사람이 현상, 원인 추정, 코드 변경, 운영 시 확인 방법을
한 번에 이해할 수 있도록 작성했다.

## 시스템 개요

IO Board API는 USB serial 포트로 보드와 통신하고 REST API와 SSE를 제공한다.

- `RQ/IW`: 로드셀 10채널 무게 조회. `/loadcells`, loadcell SSE, recording,
  `/health`의 loadcell 점검에 사용한다.
- `RQ/ID`: 문과 deadbolt 상태 조회. `/health`, `/door`, `/deadbolt`, door SSE,
  ErrorStateManagement에 사용한다.
- `MC/DC`: deadbolt 열기/닫기 제어.
- `MC/LZ`: 빈 선반 상태에서 모든 loadcell 영점 보정(calibrate).

모델/Edge는 SSE의 무게 변화를 상품 인식 및 결제 판정에 사용한다. 따라서
loadcell 값은 빠르게 전달되어야 하지만, 잘못된 serial response 또는 이전 세션의
처리 상태가 섞여서는 안 된다.

## 확인된 이슈

### 1. Serial response mismatch

보드는 가끔 현재 요청이 아니라 직전 요청의 완전한 response를 보낸다.

```text
TX RQ/IW -> RX RQ/ID
TX RQ/ID -> RX RQ/IW
```

수신 frame은 길이, CMD/SUBCMD, XOR checksum 모두 유효하며, 동시에 여러
코루틴이 포트를 쓰는 문제는 아니다. 로그에서 아래 패턴으로 확인된다.

```text
Unexpected response CMD/SUBCMD: expected=RQ/IW got=RQ/ID
Serial transaction recovered: attempt=2/3
```

현재 가장 유력한 원인은 보드 펌웨어 또는 USB serial 경로가 직전 response buffer를
늦게 전송하거나 재사용하는 것이다. 펌웨어 수정이 불가능하므로 API는 host에서
잘못된 frame을 전달하지 않도록 방어한다. 자세한 근거와 timing 실험은
[`docs/KNOWN_RESPONSE_MISMATCH.md`](docs/KNOWN_RESPONSE_MISMATCH.md)에 있다.

### 2. Loadcell sign glitch와 작은 영점 노이즈

보드는 빠른 `RQ/IW` 요청에서 일부 채널의 부호가 반전된 값을 보고할 수 있다.
또한 빈 상태에서도 수 g 수준의 노이즈가 발생한다. API는 다음을 적용한다.

- `RQ/IW` 실제 serial 전송 간격을 최소 `0.75s`로 제한한다.
- 빠른 중복 호출은 최근 sanitize된 frame을 반환한다.
- 크기가 거의 같고 부호만 반전된 값은 이전 부호로 복원한다.
- 출력은 기본적으로 5g 단위로 양자화하고 hysteresis로 경계 진동을 줄인다.

보정이 발생하면 다음 INFO 로그가 남는다.

```text
Loadcell sanitizer corrected frame:
device_values=[...]
sanitized_values=[...]
```

`device_values`는 보드가 전송한 값이고 `sanitized_values`가 REST/SSE/recording에
전달되는 값이다. 두 값을 비교하면 보드 입력 이상과 API 처리 결과를 구분할 수 있다.

### 3. Calibrate 이후 이전 값이 다음 세션에 영향

sanitizer는 부호 글리치 판별을 위해 직전 frame을 기억한다. 이전에는 `MC/LZ`
성공 후에도 이 상태와 loadcell throttle cache가 유지됐다. 따라서 보정 전의
예를 들어 `-110g`이 보정 후 첫 `+110g` frame의 부호를 잘못 복원할 가능성이
있었다.

이는 결제 중 calibrate가 실행되는 문제와는 다르다. 결제 시작 직전에 calibration이
수행된 경우, 이전 세션의 sanitizer 상태가 새 세션 첫 frame에 남을 수 있는 문제다.

### 4. Deadbolt 상태 확인이 너무 이른 문제

과거 `/deadbolt`는 `MC/DC` 이후 0.5초만 기다린 뒤 단 한 번 `RQ/ID`로 상태를
확인했다. actuator가 더 늦게 움직이면 API가 `LOCKED`를 반환하고 Edge가 open
동작을 실패로 처리할 수 있었다.

## 적용된 변경

### Serial transaction 보호

파일: [`src/services/io_board/serial_io.py`](src/services/io_board/serial_io.py)

- serial mutex는 request, response 검증, retry 전체를 소유한다.
- 수신 response의 CMD/SUBCMD와 checksum을 검증한다.
- 실제 mismatch 또는 checksum 손상이면 frame을 폐기하고 동일 요청을 최대 3회까지
  재시도한다.
- `RQ/IW` retry도 0.75초 wire 간격을 지킨다.
- transaction ID, 직전 TX, TX 간격, RX-to-TX 간격, frame hex를 로그에 남긴다.

중요: `RQ/IW -> RQ/ID` 같은 명령 전환 자체를 오류로 처리하지 않는다. 실제로
응답 header가 요청과 다를 때만 재시도하며, 3회 모두 실패할 때만 통신 오류로
처리한다.

### Deadbolt 실제 상태 확인

파일: [`src/api/v1/routers/machine.py`](src/api/v1/routers/machine.py)

- `/deadbolt`는 `MC/DC` 후 0.5초 settle을 기다린다.
- 이후 기대 상태에 도달할 때까지 0.1초 간격으로 실제 `RQ/ID`를 재조회한다.
- 대기 상한은 `IO_BOARD__HEALTH__DEADBOLT_APPLY_TIMEOUT_SECONDS`의 기본값 5초다.
- `/health`는 상태 cache를 사용하지 않고 요청할 때마다 실제 `RQ/ID`를 보낸다.

### Calibration 이후 loadcell 처리 상태 reset

파일: [`src/services/io_board/commands.py`](src/services/io_board/commands.py),
[`src/services/io_board/sanitizer.py`](src/services/io_board/sanitizer.py)

`POST /calibrate`가 성공하면 다음을 수행한다.

1. loadcell throttle cache를 비운다.
2. sanitizer의 이전 값, 부호 flip streak, quantization bin 상태를 모두 reset한다.
3. 다음 `RQ/IW`는 보정 이후 새 보드값으로 처리한다.

로그:

```text
Loadcell sanitizer state and throttle cache reset after calibration
```

### Loadcell 활성 중 IO status polling 완화

파일: [`src/main.py`](src/main.py),
[`src/services/polling/polling_service.py`](src/services/polling/polling_service.py),
[`src/core/config.py`](src/core/config.py)

loadcell SSE 또는 recording 구독이 있는 동안 background `RQ/ID` polling 주기를
`0.5s`에서 기본 `2.0s`로 늘린다. 목적은 실시간 `RQ/IW`와 `RQ/ID`의 교차 횟수를
줄여 response mismatch 가능성을 낮추는 것이다.

- loadcell polling은 기존 `0.8s`를 유지한다.
- `/health`와 `/deadbolt`의 직접 `RQ/ID` 조회는 cache나 이 간격을 사용하지 않는다.
- loadcell 구독이 없으면 background `RQ/ID`는 기존 `0.5s`로 동작한다.

설정:

```bash
IO_BOARD__POLLING__IO_STATUS_POLL_INTERVAL_WHILE_LOADCELLS_ACTIVE=2.0 \
uv run src/main.py
```

## 모델/Edge와의 책임 경계

IO Board API는 유효한 최신 loadcell frame을 빠르게 전달하고, corrupt/mismatched
serial response와 calibration 이전 처리 상태를 차단한다.

상품 결제의 최종 delta 판정은 모델/Edge 책임이다. 특히 `ses-7`, `ses-15`처럼
끝부분 하중이 안정되지 않은 경우 모델은 마지막 level을 잘못 선택할 수 있다.
모델 측에서 필요한 보호는 다음과 같다.

- 채널별 terminal plateau의 마지막 3개 이상 샘플 median을 종료값으로 사용한다.
- 냉동은 span `max(samples)-min(samples) <= 10g`, 냉장은 `<= 5g`일 때만 종료
  plateau를 안정으로 인정한다.
- 최소 3개 샘플(현재 0.8초 polling 기준 약 2.4초)이 확보되지 않으면
  `final_delta_unstable`을 기록한다.
- 불안정한 최종값으로 `unmatched_return`을 확정하지 않는다.

IO Board 변경만으로 모델의 종료 plateau 선택 문제를 해결할 수는 없다. Edge는
문 닫힘 직후 loadcell SSE/recording을 바로 끊지 말고, 최소 2.4초 동안 유지해
모델에 종료 안정값 후보를 제공해야 한다.

## 운영 확인 절차

### 서비스 시작 직후

아래 로그가 확인되어야 한다.

```text
Loadcell sanitizer enabled: ...
Loadcell throttle enabled: min gap 0.75s
Serial configured: ... inter_command_gap=0.1s
```

### Calibration

선반을 비운 후 실행한다.

```bash
curl -i -X POST http://localhost:8000/calibrate
```

성공 응답 후 다음 로그가 있어야 한다.

```text
Loadcell sanitizer state and throttle cache reset after calibration
Loadcells calibrated
```

### 무게 이상 재현과 수집

```bash
curl -X POST http://localhost:8000/recording/start
# 물체 올리기/꺼내기/놓기 재현
curl -X POST http://localhost:8000/recording/stop
curl http://localhost:8000/recording/data
```

문제 구간의 API 로그와 모델 세션 YAML을 같은 시각 기준으로 보관한다. 확인할
항목은 다음과 같다.

- `Loadcell sanitizer corrected frame`의 device/sanitized 값 차이
- `Unexpected response CMD/SUBCMD`와 `Serial transaction recovered` 발생 시각
- 모델 YAML의 start/end level, segment, final delta, 안정성 정보
- door close 후 마지막 3개 이상의 loadcell frame 존재 여부

## 검증된 테스트

현재 변경과 관련해 아래 focused test가 통과했다.

```bash
uv run pytest -q \
  tests/test_throttle_standalone.py \
  tests/test_sanitizer_standalone.py \
  tests/test_serial_transaction_standalone.py \
  tests/test_config_standalone.py \
  tests/test_machine_health_deadbolt_standalone.py
```

주요 회귀 검증:

- calibration 후 cache를 버리고 새 `RQ/IW`를 요청하는지
- sanitizer가 capture된 동크기 부호 반전을 복원하는지
- serial mismatch가 동일 transaction 안에서 retry되는지
- deadbolt가 늦게 상태를 반영해도 확인될 때까지 기다리는지
- loadcell 구독 시 background IO status polling이 적응형 간격을 쓰는지

## 남은 제한 사항

- 보드가 이전 response를 보내는 firmware/transport 결함은 host에서 완전히 고칠 수
  없다. 현재는 잘못된 frame을 폐기하고 재시도한다.
- `IO_BOARD__SERIAL__INTER_COMMAND_GAP`을 0.5초까지 올리면 mismatch는 줄지만
  loadcell 실시간성이 떨어져 기본값으로 사용하지 않는다. 기본값은 `0.1s`다.
- 큰 단발 하중 변화는 실제 상품 이동과 구분할 정보가 부족하므로 sanitizer가 임의로
  제거하지 않는다. 모델의 terminal plateau 검증이 최종 방어 계층이다.
- `calibrate`는 결제 중 실행하면 안 되며, 반드시 빈 선반에서만 수행한다.