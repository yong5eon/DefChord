# Application 생명 주기 훅 구현 기록

## 개요

[요구사항 명세서](./REQUIREMENTS.md)와 [구현 계획서](./PLAN.md)에 따라 Application 생명 주기 및 요청 경계 훅을 구현했다. 이 기록은 공개 계약, 주요 동작, 변경 파일과 검증 결과를 정리한다.

## 구현 내용

### 공개 훅 인터페이스

모든 훅은 `__call__`을 호출 진입점으로 사용하며, Application 인스턴스는 훅에 전달하지 않는다.

| 인터페이스 | 전달 인자 | 반환값 |
| --- | --- | --- |
| `ApplicationStartup` | 없음 | `None` |
| `ApplicationCleanup` | 없음 | `None` |
| `ApplicationRequest` | `Request` | `Request` |
| `ApplicationRequestResponse` | `Request`, `Optional[Response]` | `Optional[Response]` |
| `ApplicationRequestError` | `Request`, `Exception` | `None` |

`Application` 생성자는 `on_startup`, `on_cleanup`, `on_request`, `on_request_response`, `on_request_error`를 받는다. 각 입력은 해당 인터페이스 단일 인스턴스 또는 그 인터페이스의 시퀀스만 허용한다. 생략한 입력은 빈 시퀀스가 되고, 명시적 `None`이나 잘못된 타입·시퀀스 원소는 `TypeError`가 된다. 내부에서는 등록 순서를 보존한 튜플로 저장한다.

### 호출 순서와 오류 동작

- 시작 시 Application 시작 훅을 실행한 뒤 Extension을 등록 순서대로 시작한다.
- 종료 시 Extension을 역순으로 정리한 뒤 Application 정리 훅을 실행한다. 정리 실패가 있어도 나머지 정리를 시도하며, 첫 오류를 호출자에게 전파한다.
- 요청 처리에서는 Application 요청 훅이 디스패치보다 먼저 실행된다. 각 훅이 반환한 Request는 다음 훅과 디스패치에 전달된다.
- 정상 응답은 Application 응답 훅에 순서대로 전달된다. 직접 출력 경로의 응답은 `None`이며, 이 경우 훅은 새 응답으로 대체할 수 없다.
- 요청 처리 중 오류는 Application 오류 훅에 전달하고 원래 오류를 전파한다. 오류 훅에서 발생한 오류도 호출자에게 전파한다.
- Application 훅 안에서 같은 Application의 시작, 종료 또는 요청 처리를 동기 재호출하면 `RuntimeError`로 거부한다. 서로 다른 스레드의 독립 요청은 허용하며 훅 인스턴스 상태의 동기화는 사용자 책임이다.

### 서버 시작 출력 및 샘플

Python 및 Uvicorn 서버는 서버 시작 안내를 출력한 다음 `Application.start()`를 호출한다. 따라서 Application 시작 훅 로그는 서버 배너와 listen 정보 뒤에 출력된다. Gunicorn은 서버 준비 안내와 워커 시작 순서가 이미 이 동작에 맞아 별도 변경하지 않았다.

[샘플](../../samples/Sample.py)은 다섯 훅을 `Sample` 로거에 연결한다. 로깅은 INFO 수준으로 stdout에 설정해 시작 안내와 로그를 같은 출력 스트림에서 확인할 수 있다.

## 변경 파일

- [Application 구현](../../src/Application.py): 다섯 훅 인터페이스, 입력 검증, 훅 실행 및 순서·예외·재진입 처리를 추가했다.
- [공개 API](../../src/__init__.py): 다섯 훅 인터페이스를 패키지 공개 심볼로 추가했다.
- [Python 서버 어댑터](../../src/Adapter/Implements/Python/Server.py), [Uvicorn 서버 어댑터](../../src/Adapter/Implements/Uvicorn/Server.py): 서버 안내와 Application 시작 순서를 조정했다.
- [Application 훅 테스트](../../tests/test_application_hooks.py), [서버 테스트](../../tests/test_server.py), [어댑터 테스트](../../tests/test_adapters.py): 계약과 호출 순서, 오류 및 회귀 동작을 검증하도록 추가·수정했다.
- [샘플](../../samples/Sample.py): 훅 로깅 예제와 stdout 로그 설정을 추가했다.

## 검증 결과

- 전체 테스트: **153개 통과, 5개 건너뜀**.
- 수정한 Python 파일의 `py_compile` 검사 통과.
- `git diff --check` 통과.
- 샘플 실행에서 서버의 `Starting` 안내가 `INFO:Sample:Application started`보다 먼저 출력되는 것을 확인했다.
