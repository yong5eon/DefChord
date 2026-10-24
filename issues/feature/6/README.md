# RequestRunner 훅 변경 로그

## 추가

- `RequestRunnerRequest`, `RequestRunnerRequestResponse`, `RequestRunnerRequestError`를 공개했다.
- 클래스 선언의 `on_request`, `on_request_response`, `on_request_error`로 단일·복수 훅을 설정한다.
- 훅 입력을 검증해 순서가 유지되는 튜플로 보관하고 잘못된 입력·반환값을 명시적으로 거부한다.
- 검증·본문 처리·인스턴스 생성부터 핸들러 실행·응답 후처리까지 오류를 관찰하는 훅을 추가했다.

## 변경

- 요청 훅은 검증·본문 처리·생성 후 `run()` 직전에 실행한다.
- Response 반환 시에는 RunRequest가 응답 훅을 직접 실행한다.
- stream·chunked·SSE 직접 출력은 ResponseWriter에 주입한 콜백을 begin의 헤더 전송 전에 실행한다. WebSocket은 upgrade의 101 응답 전 같은 후처리를 수행한다.
- 응답 훅 뒤 CORS를 적용하고 출력별 본문·Content-Length·101 제약을 검증한다.
- 콜백은 실행 종료 시 해제하고 반환·종료·서버 전송에서 중복 실행하지 않는다.
- 응답 교체·실패 경로의 본문 자원을 정리하고 정리 실패로 원래 처리 오류가 사라지지 않게 했다.

## 제거 및 이전 주의사항

- RequestFilter·ResponseFilter와 클래스 인자 onRequest·onResponse를 제거했다. 새 인터페이스·스네이크 케이스 인자로 이전해야 한다.
- 요청 훅의 조기 응답 튜플은 지원하지 않는다. Request만 반환해야 한다.
- writer의 응답 콜백은 on_response 대신 on_request_response를 사용한다.
- 직접 출력 응답 훅도 실제 Response를 받고 반환한다. Application·Extension의 Optional[Response] 완료 훅과는 구분한다.
- 응답 훅은 전송·전체 실행 완료가 아니다. 응답 시작 후 실행 실패 시 오류 훅이 뒤이어 호출될 수 있다.
- 반환 이후 서버의 본문 소비·전송 실패는 종료된 RequestRunner 오류 훅에 재통지하지 않는다.

## 샘플 로그

- [Streaming 샘플](../../../samples/runners/Streaming.py)의 6개 핸들러와 [Requests 샘플](../../../samples/runners/Requests.py)의 5개 핸들러에 세 훅을 모두 연결했다.
- `Sample.Streaming`, `Sample.Requests` 로거에 요청·응답은 INFO, 오류는 ERROR와 traceback을 기록한다.
- 요청 ID·메서드·URI로 로그를 연결하고 응답에는 상태 코드를 기록한다. 스트리밍 응답에는 X-Request-ID 헤더도 추가한다.
- 정상은 요청 → 응답, 실행 실패는 요청 → 오류, 응답 시작 후 실패는 요청 → 응답 → 오류 순서로 확인할 수 있다.
- 검증 실패는 run 직전 요청 훅보다 먼저 발생하므로 오류 훅만 호출될 수 있다.

## 검증

- 핵심 구현 전체 회귀: 총 **218개 중 213개 성공, 5개 skip**.
- 후속 샘플 세 훅·로그 보강 후 관련 테스트: **33개 성공**.
- 확인한 핵심 소스·샘플의 Pylance 진단, 테스트 구문 및 공백 검사 통과.
- 5개 skip은 Gunicorn/POSIX 관련 환경 제약이다. 후속 샘플 변경 후 전체 회귀 재실행 및 다른 Python 버전·배포 산출물 검증은 수행하지 않았다.

## 관련 문서

- [요구사항 명세서](./REQUIREMENTS.md)
- [작업 계획서](./PLAN.md)
- [상세 구현 기록](./IMPLEMENTS.md)
