# Application 생명 주기 훅 구현 계획서

## 1. 준비 상태

구현을 시작할 준비가 되었다. 훅 이름과 생성자 인자, 호출 시그니처, 입력 타입, Application과 Extension 사이의 시작·정리 순서, 요청 훅 순서, 예외 처리, 재진입 금지 조건이 [요구사항 명세서](./REQUIREMENTS.md)에 확정되어 있다. 추가 사용자 결정은 필요하지 않다.

이 계획은 `feature/4`의 Application 훅 구현과 검증을 다룬다. Extension 및 RequestRunner 전용 훅 자체를 새로 구현하는 것은 각 하위 이슈의 범위로 유지하되, 해당 훅이 추가될 때 정해진 호출 순서를 만족하도록 Application 연결 지점을 구성한다.

## 2. 구현 대상

### 공개 인터페이스

다섯 인터페이스를 `__call__`만 구현 계약으로 정의하고 공개 API로 내보낸다.

| 인터페이스 | 호출 인자 | 반환값 |
| --- | --- | --- |
| `ApplicationStartup` | 없음 | `None` |
| `ApplicationCleanup` | 없음 | `None` |
| `ApplicationRequest` | `Request` | `Request` |
| `ApplicationRequestResponse` | `Request`, `Optional[Response]` | `Optional[Response]` |
| `ApplicationRequestError` | `Request`, `Exception` | `None` |

각 인터페이스에는 위 표에 없는 실행 컨텍스트나 Application 인자를 추가하지 않는다.

### 생성자 인자

`Application.__init__`에 다음 인자를 추가한다.

- `on_startup`
- `on_cleanup`
- `on_request`
- `on_request_response`
- `on_request_error`

각 인자는 해당 인터페이스 단일 인스턴스 또는 해당 인터페이스만 담은 `Sequence`만 허용한다. 인자 생략 시 빈 시퀀스를 사용하며, 명시적 `None`, 잘못된 인터페이스 또는 잘못된 시퀀스 원소는 `TypeError`로 거부한다. 내부에는 순서가 보존된 튜플로 저장한다.

## 3. 작업 단계

### 1단계: 인터페이스와 공개 export 추가

- [Application.py](../../../src/Application.py)에 다섯 훅 인터페이스를 정의한다.
- 각 인터페이스의 `__call__` 시그니처와 반환 타입을 명세와 일치시킨다.
- [패키지 공개 API](../../../src/__init__.py)에 인터페이스를 import하고 `__all__`에 추가한다.
- 기존 `Application` import 및 생성자 호출이 훅 미설정 상태에서 호환되는지 확인한다.

### 2단계: 생성자 입력 검증과 저장

- 다섯 생성자 인자를 검증하고 단일 인스턴스는 1개짜리 튜플로 정규화한다.
- `Sequence` 입력은 튜플로 복사하여 입력 컨테이너의 후속 변경이 Application 설정에 영향을 주지 않게 한다.
- `str`, `bytes`, 잘못된 타입 및 인터페이스 계약이 맞지 않는 원소를 거부한다.
- 명시적 `None`을 빈 값으로 취급하지 않고 `TypeError`로 거부한다.

### 3단계: 시작·종료 훅 연결

- `start()`에서 중복 시작 검사를 먼저 수행한 다음 Application 시작 훅을 등록 순서대로 호출한다.
- Application 시작 훅이 모두 성공한 뒤 Extension을 기존 등록 순서대로 시작한다.
- Application 시작 훅 실패 시 Extension 시작과 Application 정리 훅을 실행하지 않고 해당 오류를 전파한다.
- Extension 시작 실패 시 이미 시작한 Extension을 기존처럼 역순 정리하고 시작 오류를 전파한다. 이 경로에서는 Application 정리 훅을 호출하지 않는다.
- `stop()`에서 실행 상태를 먼저 종료 상태로 전환하고 Extension을 등록 역순으로 정리한 뒤 Application 정리 훅을 호출한다.
- 한 정리 훅의 실패로 후속 Extension 또는 Application 정리를 건너뛰지 않는다. 정리를 모두 시도한 뒤 첫 오류를 전파하고 추가 오류를 로그에 남긴다.
- 실행 중이 아닌 `stop()`은 기존처럼 아무 정리 훅도 실행하지 않는다.

### 4단계: 요청 처리 훅 연결

- `Application.__call__`의 처리 경계를 감싸서 요청 훅, 디스패치, 응답 훅 또는 오류 훅을 한곳에서 관리한다.
- Application 요청 훅은 라우팅과 RequestRunner 실행에 앞서 등록 순서대로 호출하고, 반환된 Request를 다음 훅 및 디스패치에 전달한다.
- 정상 완료 후 Application 응답 훅을 등록 순서대로 호출하고, 반환된 Response를 다음 훅 및 호출자에게 전달한다.
- 직접 출력 경로에서는 응답 훅에 `None`을 전달하며 훅도 `None`을 반환해야 한다.
- 디스패치 또는 요청 훅에서 예외가 발생하면 Application 오류 훅을 등록 순서대로 호출한 뒤 요청 예외를 그대로 전파한다.
- 오류 훅에서 발생한 예외는 호출자에게 전파하되 원래 요청 예외를 예외 체인에 보존한다.
- 하위 RequestRunner 및 향후 Extension 요청 훅이 존재하는 경우 Application Request → 하위 훅 → Application Response/Error 순서를 유지한다. 기존 Extension `begin/end`는 이 순서 계약에 포함하지 않고 위치를 변경하지 않는다.

### 5단계: 동기 재진입 차단

- Application 훅 실행 중 동일 Application의 `start()`, `stop()`, `__call__()`에 동기 재호출이 발생하면 `RuntimeError`로 거부한다.
- 요청별 독립 호출이 다른 스레드에서 동시에 수행되는 것은 차단하지 않는다.
- 훅 객체 자체에 대한 잠금이나 사용자 상태 동기화 기능은 추가하지 않는다.

### 6단계: 문서와 회귀 테스트

- [요구사항 명세서](./REQUIREMENTS.md)에 정의된 호출·순서·오류 계약을 API 문서 및 예제로 반영한다.
- 단위 테스트로 인터페이스 시그니처, 생성자 입력 검증, 단일·복수 훅 정규화, 실행 순서, 변환 결과 전달, 예외 및 재진입을 검증한다.
- 시작·정리 테스트에서 Extension 순서, 역순 정리, 정리 오류 후 Application 종료 상태 및 오류 전파를 검증한다.
- 기존 서버 어댑터 테스트로 Python, Uvicorn, Gunicorn 경로의 시작·종료 훅 중복 여부와 기존 동작 회귀를 확인한다.
- 공개 API 테스트를 실행해 와일드카드 import와 `__all__` 계약을 확인한다.

## 4. 예상 변경 파일

| 파일 | 변경 내용 |
| --- | --- |
| [Application.py](../../../src/Application.py) | 훅 인터페이스, 생성자 인자 검증·저장, 생명 주기 및 요청 경계 실행 |
| [__init__.py](../../../src/__init__.py) | 다섯 훅 인터페이스 공개 export |
| [test_application_hooks.py](../../../tests/test_application_hooks.py) | Application 훅 단위 및 경계 동작 테스트 신규 작성 |
| [test_server.py](../../../tests/test_server.py) | 서버 경로의 시작·정리 통합 회귀 테스트 보강 |
| [test_exports.py](../../../tests/test_exports.py) | 필요한 경우 공개 심볼 검증 보강 |
| [README.md](../../../README.md) | 훅 설정 및 간단한 사용 예제 추가 |

## 5. 검증 계획

1. 신규 Application 훅 테스트를 우선 실행한다.
2. [서버 테스트](../../../tests/test_server.py), [Extension 테스트](../../../tests/test_extensions.py), [공개 API 테스트](../../../tests/test_exports.py)를 함께 실행한다.
3. 위 선택 테스트가 통과하면 DefChord 전체 테스트를 실행해 기존 동작 회귀 여부를 확인한다.
4. 실제 검증 명령은 저장소에서 사용하는 테스트 실행 설정을 확인한 뒤 선택 테스트와 전체 테스트에 동일한 runner를 사용한다.

## 6. 완료 조건

- 다섯 인터페이스와 생성자 인자명이 명세와 동일하다.
- Application 인스턴스는 훅에 전달되지 않으며 요청·응답·오류 인자와 반환 계약이 정확하다.
- 입력 검증, 등록 순서, Application/Extension 수명 순서, 요청 훅 계층 순서, 오류 전파 및 동기 재진입 차단이 테스트로 확인된다.
- 정리 오류가 발생해도 모든 정리를 시도하고 Application은 종료 상태가 된다.
- 모든 관련 테스트와 전체 회귀 테스트가 통과하며 공개 사용법이 문서화되어 있다.
