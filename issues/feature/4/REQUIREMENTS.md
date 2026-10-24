# Application 생명 주기 훅 요구사항 명세서

## 1. 목적과 범위

이 문서는 [Application 생명 주기 훅 추가 이슈](./ISSUE.md)의 요구사항을 정리한다. 상위 이슈의 공통 결정과 현재 소스 동작을 바탕으로 Application이 제공해야 할 훅의 책임 경계, 동작 요구사항, 수용 기준을 정의한다.

대상은 다음 Application 수명 경계이다.

- Application 시작
- Application의 요청 처리 진입, 정상 응답 반환 및 오류
- Application 종료

Extension 자체의 생명 주기·요청 관찰 훅과 RequestRunner의 개별 핸들러 실행 훅은 이 문서의 구현 범위가 아니다. 관련 작업은 상위 이슈에서 구분한 [feature/5](../5/REQUIREMENTS.md)(Extension), `feature/6`(RequestRunner)에서 다룬다.

후속 feature/5는 생성된 Extension 인스턴스 등록과 생성자 훅을 구현했다. Application 시작 훅 다음에 각 Extension의 `startup(application)`으로 연결·라우트 등록·자원 준비를 수행하고, 종료 시에는 Extension의 `cleanup()` 다음에 Application 정리 훅을 실행한다. Factory·별도 `bind/route/routes`는 두지 않는다. 아래 기존 `begin/end` 보존 설명은 feature/4 구현 당시 범위이며 최신 Extension 계약은 feature/5가 대체한다. 로고는 시작 로그보다 먼저 출력하고 Extension 라우트 대신 등록된 인스턴스의 `str(extension)` 표시값·개수를 안내한다.

## 2. 근거 문서

- [상위 이슈](../2/ISSUE.md)
- [상위 공통 요구사항 명세서](../2/REQUIREMENTS.md)
- [Application 구현](../../../src/Application.py)
- [공통 서버 요청 처리기](../../../src/Adapter/RequestHandler.py)
- [서버 어댑터 계약](../../../src/Adapter/Server.py)
- [Python 서버](../../../src/Adapter/Implements/Python/Server.py)
- [Uvicorn 서버](../../../src/Adapter/Implements/Uvicorn/Server.py)
- [Gunicorn 서버](../../../src/Adapter/Implements/Gunicorn/Server.py)
- [서버 수명 주기 테스트](../../../tests/test_server.py)

## 3. 현재 동작 분석

아래 내용은 변경 전 구현에 대한 조사이며, 새 훅의 호출 계약을 의미하지 않는다.

### 3.1 구성

- `Application.__init__`은 라우터와 확장 등록 상태를 구성하고, 확장 라우트를 등록한 뒤 각 확장을 Application에 바인딩한다.
- 확장은 한 Application에만 소속될 수 있으며, 구성 중 오류가 발생하면 예외가 호출자에게 전파된다.
- Application 생성자에는 사용자 생명 주기 콜백을 전달하는 매개변수가 없다.

### 3.2 시작 및 종료

- `start()`는 실행 중 중복 호출을 거부하고, 확장을 등록 순서대로 시작한다.
- 확장 시작 중 오류가 발생하면 먼저 시작된 확장들을 역순으로 정리한 뒤 원래 오류를 전파한다. 정리 오류는 로그로 남긴다.
- `stop()`은 실행 중이 아닐 때 아무 작업도 하지 않는다. 실행 중이면 확장을 역순으로 종료하고, 모든 종료를 시도한 뒤 첫 오류를 전파한다.
- Extension의 애플리케이션 수명 훅은 `start(app)`와 `stop(app)`이다. `begin(request)`와 `end(request, ...)`는 서버 요청 처리 경로에서 실행되는 요청별 관찰 메서드이며 Application 시작·정리 훅이 아니다.
- Python 및 Uvicorn 어댑터는 서버 실행 중 Application을 시작·종료한다. Gunicorn 어댑터는 워커 초기화 및 종료 경로에서 시작·종료한다.

### 3.3 요청 디스패치

- `Application.__call__(request)`은 `OPTIONS` 처리, 라우트 탐색, 요청 조건 검증 및 RequestRunner 위임을 수행한다.
- 라우트 없음, 허용되지 않은 메서드, 잘못된 요청 조건은 디스패치 과정에서 오류로 끝날 수 있다.
- 직접 호출은 Application의 `running` 상태를 검사하지 않는다.
- 서버 요청 경로는 공통 요청 처리기가 `Application(request)`를 호출한다. 확장의 요청 관찰은 이 공통 서버 경로에 별도로 연결되어 있다.
- Application 요청 훅은 현재 없다. 따라서 Application의 디스패치 경계와 서버의 요청 수신·응답 전송 경계를 혼동하지 않아야 한다.

## 4. 설계 원칙

1. 훅은 Application 자신의 생명 주기와 요청 처리 경계에만 속한다.
2. 훅 계약은 Application 생성자에서 설정하며, 인터페이스 이름에는 `Application` 접두사를 사용한다.
3. 각 이벤트에 훅을 하나 또는 여러 개 연결할 수 있어야 한다.
4. 훅이 설정되지 않은 Application은 기존 동작을 유지해야 한다.
5. 잘못된 훅 입력이나 훅 실행 오류를 조용히 무시하거나 성공으로 가장해서는 안 된다.
6. 훅 인스턴스는 동일 Application의 동시 요청에서 공유될 수 있으므로 훅의 가변 상태 및 동시성 계약을 문서화해야 한다.

## 5. 확정된 공개 이름

Application 생성자는 아래 다섯 이벤트에 대응하는 훅 인자를 제공한다. 각 입력 타입은 `Union[Hook, Sequence[Hook]]`이다. `None` 등 이 타입에 해당하지 않는 값은 허용하지 않는다. 인자를 생략하면 기본 빈 시퀀스를 사용한다. 단일 훅은 1개짜리 내부 튜플로 정규화하고, 복수 입력 시퀀스는 불변 튜플로 복사한다.

| 인터페이스 | 생성자 인자 | 책임 |
| --- | --- | --- |
| `ApplicationStartup` | `on_startup` | Application 시작 시 실행한다. |
| `ApplicationCleanup` | `on_cleanup` | Application 종료 시 실행한다. |
| `ApplicationRequest` | `on_request` | 요청이 Application 처리 경계에 진입할 때 실행한다. |
| `ApplicationRequestResponse` | `on_request_response` | Application이 요청 처리를 정상 완료해 응답을 반환할 때 실행한다. |
| `ApplicationRequestError` | `on_request_error` | Application 요청 처리 경계 안에서 예외가 발생했을 때 실행한다. |

인터페이스 이름은 `Application` 접두사와 구체적인 이벤트 이름을 조합한다. 생성자 인자는 `on_` 접두사를 붙인 소문자 스네이크 케이스를 사용한다. `Dispatch`는 공개 이름에 포함하지 않는다.

`ApplicationRequestResponse`는 응답 전송 완료를 뜻하지 않는다. 응답을 반환하는 Application 처리 경계가 끝난 시점을 의미한다. `ApplicationRequestError`는 요청 처리 오류에만 적용하며, Application 시작·종료 오류를 포괄하는 일반 오류 훅은 제공하지 않는다. 시작·종료 오류는 해당 호출자에게 전파한다.

### 5.1 인터페이스 호출 계약

모든 인터페이스는 `__call__`만 훅 진입점으로 제공한다.

| 인터페이스 | `__call__` 시그니처 | 반환 계약 |
| --- | --- | --- |
| `ApplicationStartup` | `()` | `None` |
| `ApplicationCleanup` | `()` | `None` |
| `ApplicationRequest` | `(request: Request)` | `Request` |
| `ApplicationRequestResponse` | `(request: Request, response: Optional[Response])` | `Optional[Response]` |
| `ApplicationRequestError` | `(request: Request, error: Exception)` | `None` |

Application 인스턴스는 훅 인자로 전달하지 않는다. `ApplicationRequest`의 반환 Request는 이후 요청 처리와 다음 요청 훅에 사용한다. `ApplicationRequestResponse`는 현재 응답을 반환값으로 교체할 수 있다. 입력 응답이 `None`인 직접 출력 경로에서는 이미 응답 전송이 완료된 상태이므로 훅도 `None`을 반환해야 하며 새 Response를 만들 수 없다. `ApplicationRequestError`는 오류를 관찰하며 응답을 반환하거나 대체하지 않는다.

## 6. 기능 요구사항

### APP-01. 생성자 기반 계약

Application은 생성자에서 `on_startup`, `on_cleanup`, `on_request`, `on_request_response`, `on_request_error`를 받아야 한다. 각 입력은 `Union[해당 인터페이스, Sequence[해당 인터페이스]]`만 허용한다. 인자 생략 시 기본 빈 시퀀스를 사용하고, `None`, 다른 타입 또는 해당 인터페이스가 아닌 시퀀스 원소는 `TypeError`로 거부한다.

잘못된 타입이나 지원하지 않는 입력 형태는 구성 시 명시적인 예외로 거부해야 한다.

단일 입력이든 복수 입력이든 Application 내부 저장 형식은 해당 이벤트의 훅 시퀀스로 통일한다. 복수 훅은 등록된 순서대로 실행한다. 요청 변환 훅은 각 훅의 반환 Request를 다음 훅과 디스패치에 전달하며, 응답 훅은 각 훅의 반환 응답을 다음 훅에 전달한다.

### APP-02. 시작 이벤트

Application이 시작되는 시점을 사용자가 처리할 수 있어야 한다. 기존 `start()` 중복 시작 방지 및 확장 시작 동작과 일관되어야 하며, 시작 이벤트의 호출 여부와 순서는 확장 시작·실패 롤백 동작과 함께 명시되어야 한다.

Application의 `ApplicationStartup` 훅은 소속 Extension의 시작 훅보다 먼저 실행되어야 한다. Application 시작 훅이 성공한 뒤 Extension 시작 처리를 진행한다.

Application의 시작 훅이 실패하면 해당 예외를 호출자에게 그대로 전파하고, Application 정리 훅이나 Extension 시작 훅은 호출하지 않는다. Application 시작 훅이 성공한 뒤 Extension 시작 중 실패하면 기존 계약대로 이미 시작된 Extension을 역순 정리하고 원래 시작 예외를 전파한다. 이 실패 경로에서 Application 정리 훅은 호출하지 않는다.

기존 확장 정리 동작을 훅 추가만으로 약화하거나 건너뛰어서는 안 된다.

### APP-03. 요청 이벤트

Application의 요청 처리 진입, 정상 응답 반환, 요청 처리 오류를 각각 대응하는 인터페이스로 관찰할 수 있어야 한다.

- 요청 처리 범위는 `Application.__call__` 진입부터 Response 반환 또는 오류 전파까지이다.
- 라우트 탐색 실패나 요청 검증 실패를 포함해 요청 처리 경계 안에서 발생한 오류는 `ApplicationRequestError`의 대상이다.
- 정상적으로 반환된 Response는 `ApplicationRequestResponse`의 대상이다.
- `Application(request)` 직접 호출과 서버에서 전달된 호출 모두 같은 Application 요청 훅 계약을 적용해야 한다.
- 이 훅은 연결 수립, 요청 본문 수신 전 과정, Response 전송·스트림 소비, 연결 종료를 관찰하거나 제어하지 않는다.
- Application의 `ApplicationRequest` 훅은 요청 처리와 관련된 Extension 및 RequestRunner 훅보다 먼저 실행되어야 한다. `ApplicationRequestResponse` 훅은 해당 Extension 및 RequestRunner의 정상 응답 훅이 모두 끝난 뒤 실행되어야 한다.
- 요청 실패 시 RequestRunner 및 Extension의 해당 오류 훅이 먼저 완료되고, 그 뒤 `ApplicationRequestError`가 실행되어야 한다.
- 기존 Extension `begin/end`는 별도의 서버 요청 관찰 메서드다. 현재 공통 처리기는 `begin`을 `Application(request)` 호출 전에, `end`를 응답 전송 뒤에 호출한다. `ApplicationRequest`는 `begin`보다 늦게 실행될 수 있고, `ApplicationRequestResponse`는 `end`보다 먼저 실행되므로, 위 요청 훅 순서 규칙은 기존 `begin/end`에는 적용하지 않는다. 이 이슈에서 `begin/end`의 호출 위치를 변경하지 않는다.
- 훅에서 발생한 예외를 조용히 무시하거나 응답으로 바꾸지 않고 호출자에게 예외로 전파해야 한다. Request 훅 예외는 정상적인 응답 완료로 취급하지 않는다.
- `ApplicationRequest`, `ApplicationRequestResponse` 등 요청 처리 훅 자체에서 예외가 발생해도 해당 예외를 요청 처리 오류로 보고 `ApplicationRequestError`를 호출한다. 오류 훅은 관찰 전용이며 원래 예외를 소비하거나 응답으로 변환하지 않는다. 오류 훅 자체가 실패하면 그 훅 예외를 호출자에게 전파하고, 기존 요청 예외는 예외 체인에 보존한다.

`ApplicationRequestResponse`는 Response 객체가 없는 직접 출력 경로에서 `response=None`을 받으며, 이 경우 훅도 `None`을 반환해야 한다. `ApplicationRequestError`에는 요청 처리 경계에서 발생한 `Exception`을 전달하고, 오류 응답을 생성하지 않는다.

### APP-04. 종료 이벤트

Application이 종료되는 시점을 사용자가 처리할 수 있어야 한다. 기존 `stop()`의 멱등 동작, 확장 역순 종료, 모든 확장의 종료 시도 및 종료 오류 전파와 일관되어야 한다.

소속 Extension의 정리 훅은 Application의 `ApplicationCleanup` 훅보다 먼저 실행되어야 한다. Extension 정리가 끝난 뒤 Application 정리 훅을 실행한다.

`stop()`이 실행 중이 아닌 Application에 호출되면 기존처럼 아무 작업도 하지 않으며, Application 정리 훅과 Extension 정리 훅 모두 호출하지 않는다. 시작 실패 경로에서는 시작 요구사항에 따라 Application 정리 훅을 호출하지 않는다.

정리 작업이 실패하더라도 Application은 종료 상태가 되어야 하며, 실행 상태로 남아서는 안 된다. Extension은 등록 역순으로 모두 정리하고, Extension 정리가 끝난 뒤 Application 정리 훅을 실행한다. 한 정리 작업의 실패 때문에 이후 정리를 건너뛰지 않는다. 정리 시도 후 오류가 발생했다면 기존 `stop()` 계약에 따라 첫 오류를 호출자에게 전파하고 후속 정리 오류는 기록한다.

### APP-05. 이벤트별 다중 훅

각 이벤트의 훅을 여러 개 설정할 때 다음 동작을 명세와 테스트에 포함해야 한다.

- 실행 순서
- 한 훅이 실패하면 나머지 훅은 실행하지 않고 해당 예외를 전파한다.
- 복수 훅 입력 중 유효하지 않은 항목이 있을 때의 검증 방식

훅 실행에서 발생한 예외는 감싸거나 응답으로 대체하지 않고 호출자에게 예외로 전파한다. 이벤트별 실행·오류 정책에 차이가 있으면 그 차이를 문서화해야 한다.

### APP-06. 어댑터 및 계층 일관성

Python, Uvicorn, Gunicorn 어댑터 등 Application의 기존 시작·종료 진입점은 같은 Application 훅 계약을 사용해야 한다. 서버 구현이 별도의 Application 훅 호출을 중복 추가해서는 안 된다.

Application 디스패치 훅과 Extension의 요청 관찰, 내부 Extension 라우트의 RequestRunner 실행이 겹칠 수 있는 경로를 확인하여 각 훅의 대상과 호출 횟수를 구분해야 한다.

## 7. 비기능 요구사항 및 제외 범위

- 훅이 없는 경우 기존 API 동작과 서버 실행 동작을 보존한다.
- Application은 생성자에 전달된 훅 인스턴스를 내부 시퀀스에 보관하므로, 동일 Application의 동시 요청은 같은 훅 인스턴스를 호출할 수 있다. Request와 Response는 요청별 값이지만 훅 인스턴스의 가변 상태는 공유될 수 있다.
- 프레임워크는 사용자 훅의 가변 상태를 자동으로 잠그거나 동기화하지 않는다. 사용자 정의 훅은 동시 호출에 안전하도록 구현해야 한다. 별도 프로세스 간 훅 상태 공유는 보장하지 않는다.
- 예외는 해당 생명 주기 호출자에게 전파하거나 표준 로깅으로 명시적으로 보고해야 한다. 광범위한 예외 억제나 임의 폴백을 두지 않는다.
- 훅은 클라이언트에 전달된 응답 또는 전송 완료를 의미하지 않는다.
- 연결·전송 계층 이벤트, Extension 내부 자원 이벤트, RequestRunner의 상세 파이프라인 이벤트를 Application 훅으로 중복 제공하지 않는다.
- 기존 `Extension.start/stop` 또는 `Extension.begin/end`를 제거·대체하는 작업은 이 이슈 범위에 포함하지 않는다.

### 7.1 재진입과 중복 호출

재진입은 다른 스레드나 프로세스에서 동시에 호출되는 상황이 아니라, 실행 중인 훅이 같은 Application의 메서드를 동기적으로 다시 호출하는 상황이다. 예를 들어 훅이 외부에서 보유한 참조를 통해 `start()`를 다시 호출하거나, 요청 처리 훅이 같은 Application에 중첩 요청을 전달하는 경우가 이에 해당한다.

Application 훅에서 같은 Application의 `start()`, `stop()`, `__call__()`을 동기적으로 다시 호출하는 재진입은 허용하지 않으며, 발생하면 명시적인 `RuntimeError`로 거부해야 한다. 구현은 훅 호출 경계를 추적해 중첩 호출을 감지해야 한다. 서로 다른 스레드에서 들어오는 독립 요청은 재진입이 아니며 기존 서버 동시성에 따라 처리한다. 사용자 훅 객체가 공유되는 경우의 상태 동기화는 사용자 책임이다.

훅 인터페이스에는 각 이벤트가 실제로 필요로 하는 값만 전달한다. Application 인스턴스와 별도의 실행 컨텍스트 객체는 전달하지 않으며, 훅 계약을 통해 Application을 직접 조작할 수 없도록 한다.

## 8. 수용 기준

| ID | 검증 기준 |
| --- | --- |
| AC-01 | 훅 미설정 Application의 기존 생성, 시작, 직접 요청 처리 및 종료 동작이 유지된다. |
| AC-02 | 다섯 인터페이스가 명시된 `__call__` 인자·반환 계약을 따르고, 생성자 인자가 단일·복수 입력을 처리한다. |
| AC-03 | 시작 및 정리 훅이 직접 호출과 각 서버 어댑터의 시작·종료 경로에서 중복 없이 계약된 횟수와 순서로 실행된다. |
| AC-04 | 요청 처리에서 Application 요청 훅이 RequestRunner 훅보다 먼저, 응답 훅이 정상 완료한 RequestRunner 훅 뒤에 실행된다. |
| AC-05 | 라우팅 오류, 요청 검증 오류, RequestRunner 오류 및 정상 Response/직접 출력에서 요청 훅 동작과 오류 전달이 명세대로 검증된다. |
| AC-06 | 시작·정리 및 요청 훅에서 발생한 예외가 숨겨지거나 성공 응답으로 변환되지 않고 호출자에게 전파된다. |
| AC-07 | 복수 훅의 실행 순서 및 중간 실패 동작, 동시 요청 시 공유·호출 특성이 테스트와 API 문서에 반영된다. |
| AC-08 | Extension의 서버 요청 관찰 경계와 RequestRunner 실행 경계가 구분되고 의도하지 않은 훅 중복 실행이 없다. |

## 9. 구현 적용 기준

요구사항과 공개 훅 계약은 확정되었으며, 추가로 사용자 결정이 필요한 항목은 없다. 구현 시 다음 확정 규칙을 적용한다.

- 생성자 훅 인자는 `Union[해당 인터페이스, Sequence[해당 인터페이스]]`로 제한한다. 인자를 생략하면 빈 시퀀스를 사용하고, `None`이나 잘못된 타입·원소는 `TypeError`로 거부한다. 입력 시퀀스는 튜플로 복사한다.
- 종료 시 Extension을 등록 역순으로 모두 정리한 뒤 Application 정리 훅을 실행한다. 여러 정리 작업이 실패해도 Application은 종료 상태가 되며, 첫 오류를 전파하고 후속 정리 오류는 로그에 남긴다.
- 같은 Application의 훅 실행 중 동기적으로 시작·종료·요청 처리를 다시 호출하면 `RuntimeError`로 거부한다. 서로 다른 스레드의 독립 요청은 차단하지 않는다.
