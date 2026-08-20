# IO Board

CRK 장비의 로드셀, 문 센서와 데드볼트를 제어하는 FastAPI 서비스이다.
REST API, 통합 SSE 스트림, 로드셀 기록과 시리얼 통신 복구를 제공한다.

## 시작

```bash
uv sync
uv run src/main.py
```

기본 주소는 `http://localhost:8000`이다. 현재 API 요청·응답 규격은 실행 중인
서비스의 Swagger UI(`/docs`)와 OpenAPI JSON(`/openapi.json`)을 기준으로 한다.

환경 변수와 운영 설정은 [README.PROD.md](README.PROD.md)를 참고한다.

## 문서

- [API 사용법](docs/API.md)
- [서비스 구조](docs/ARCHITECTURE.md)
- [운영 및 장애 대응](docs/OPERATIONS.md)
- [시리얼 프로토콜](docs/PROTOCOL.md)
- [테스트 구성](docs/TESTS.md)
- [미해결 시리얼 응답 불일치](docs/KNOWN_RESPONSE_MISMATCH.md)
- [로드셀 부호 글리치 펌웨어 요청](docs/FIRMWARE_SIGN_GLITCH_REQUEST.md)
- [로드셀 zero-tracking 펌웨어 요청](docs/FIRMWARE_ZERO_TRACKING_REQUEST.md)
- [변경 이력](CHANGELOG.md)

하드웨어 원본 사양은 `specs/`의 CSV와 PDF를 기준으로 한다.

## 주요 기능

- 로드셀 10채널 조회, 기록과 SSE 스트리밍
- 문·데드볼트 상태 조회와 데드볼트 제어
- exponential·Kalman filter와 threshold 변화 감지
- 시리얼 timeout retry, 응답 유형 검증과 진단 로그
- 환경 변수 기반 polling, sanitizer와 health 설정

## 테스트

```bash
uv run pytest
```

각 파일의 검증 범위는 [docs/TESTS.md](docs/TESTS.md)를 참고한다.

## License

Internal project - CRK Rewrite Initiative
