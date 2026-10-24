# Extension 생명 주기 훅 요구사항 명세서

## 1. 목적과 범위

이 문서는 [Extension 생명 주기 훅 추가 이슈](./ISSUE.md)의 요구사항을 정의한다. 상위 이슈의 공통 원칙과 Application 생명 주기 훅 계약을 Extension 경계에 적용해, 공개 훅 계약과 기존 Extension 확장점과의 관계를 명시한다.

대상은 Extension의 시작·정리와 Extension이 제공할 수 있는 라우트 및 요청 이벤트이다. Extension은 HTTP 라우트를 제공하는 기능에 한정하지 않으며, Application 수명에 맞춰 자체 자원이나 백그라운드 작업을 관리할 수도 있다. Application 전체의 수명, 서버 전송 수명, 다른 Extension 및 내부 RequestRunner의 실행 세부 사항은 대상이 아니다.

## 2. 근거 문서

- [상위 이슈](../2/ISSUE.md)
- [상위 공통 요구사항 명세서](../2/REQUIREMENTS.md)
- [Application 생명 주기 훅 이슈](../4/ISSUE.md)
- [Application 훅 요구사항 명세서](../4/REQUIREMENTS.md)
- [Application 구현](../../src/Application.py)
- [Extension 구현](../../src/Extension.py)
- [Extension 요청 실행기 생성](../../src/Runners/RunExtension.py)
- [공통 서버 요청 처리기](../../src/Adapter/RequestHandler.py)
- [Route 구현](../../src/Route.py)
- [RequestRunner 구현](../../src/RequestRunner.py)

## 3. 현재 동작 분석

### 3.1 Extension 구성과 기존 확장점

- `Extension`은 현재 하나의 `path`를 받아 인스턴스화되며, Application은 그 경로와 `methods`를 바탕으로 라우트를 만든다.
- Extension은 추상 메서드 `__call__(app, request)`를 구현해 Extension 라우트의 처리를 제공한다.
- Extension에는 `bind(app)`, `start(app)`, `stop(app)`, `begin(request)`, `end(request, context, status, error)` 메서드가 이미 있다.
- `start/stop`은 Application 시작·종료 시 호출되는 확장점이다. 서버의 공통 요청 처리기는 요청 관찰을 위해 `begin`을 등록 순서대로, 참여에 성공한 Extension의 `end`를 역순으로 호출한다.
- 생성자 인자 `onRequest`와 `onResponse`는 Extension 생명 주기 훅이 아니라 내부 RequestRunner의 요청·응답 필터에 연결된다.
- 현재 Extension에는 생명 주기 이벤트를 클래스 선언에서 등록하는 계약이 없다.

### 3.2 계층 경계

- Application은 자신의 시작·종료와 전체 요청 디스패치를 소유한다.
- ExtensionFactory는 Extension 인스턴스와 그 인스턴스의 라우트 목록을 함께 제공한다. Extension은 자신에게 연결된 라우트의 처리와 자신의 자원 수명을 소유한다.
- Application은 제공된 라우트 목록의 등록·매칭을 소유하고, 매칭된 라우트의 처리를 Extension에 위임한다.
- Extension 라우트의 `Route`-Extension 연결은 구현체가 담당한다. Extension 훅과 RequestRunner 필터·훅은 서로 다른 처리 경계로 명세해야 한다.
- `begin/end`는 서버 공통 요청 처리 경로의 관찰 메서드다. Extension 라우트가 실제로 실행되지 않는 요청에서도 호출될 수 있으므로 Extension 자체 요청 훅과 같은 이벤트로 취급할 수 없다.

## 4. 설계 원칙

1. Extension 훅은 해당 Extension의 생명 주기 또는 해당 Extension 라우트 처리 경계 안에서만 실행한다.
2. 훅 계약은 상위 명세에 따라 Extension 하위 클래스 선언 시 설정한다. Application의 훅과 같은 이벤트 모델 및 입력·반환 계약을 사용하되, 인터페이스 이름은 `Extension` 접두사를 사용한다.
3. 각 이벤트에 단일 또는 복수 훅을 설정할 수 있고, 복수 훅은 선언 순서대로 실행한다.
4. Extension은 Application에 등록할 라우트 객체의 시퀀스를 제공한다. Application은 목록을 라우터에 등록하고 요청 매칭을 수행한다.
5. Extension의 기존 `bind/start/stop/begin/end` 확장점은 제거한다. 구성·전역 요청 처리는 Application이 담당하며, Extension 수명 및 라우트 실행 이벤트는 새 훅 계약으로 제공한다.
6. 기존 RequestRunner `onRequest/onResponse` 필터 계약은 유지한다.
7. 오류를 숨기거나 훅 결과를 임의로 대체하지 않는다. 기존 Application·서버 오류 및 정리 정책과 일관되게 오류를 전파하거나 기록한다.

## 5. 공개 훅 계약

Extension은 다음 다섯 이벤트 인터페이스를 제공해야 한다. 클래스 선언에서 설정하는 이름은 Application 계약과 같은 `on_startup`, `on_cleanup`, `on_request`, `on_request_response`, `on_request_error`를 사용한다. 타입과 반환 계약은 다음과 같다.

| 인터페이스 | `__call__` 입력 | 반환값 | 책임 |
| --- | --- | --- | --- |
| `ExtensionStartup` | 없음 | `None` | 해당 Extension이 시작될 때 실행 |
| `ExtensionCleanup` | 없음 | `None` | 해당 Extension이 정리될 때 실행 |
| `ExtensionRequest` | `Request` | `Request` | 해당 Extension 라우트의 처리 직전에 요청 관찰·변환 |
| `ExtensionRequestResponse` | `Request`, `Optional[Response]` | `Optional[Response]` | 해당 Extension 처리가 정상 완료되어 응답을 반환할 때 관찰·변환 |
| `ExtensionRequestError` | `Request`, `Exception` | `None` | 해당 Extension 처리 경계에서 발생한 오류 관찰 |

인터페이스 이름은 위 표의 철자를 따른다. 특히 `ExtensionCleanup`의 철자는 `Cleanup`이다. Extension 훅은 Application 또는 Extension 인스턴스를 별도 인자로 받지 않으며, 표에 정의한 이벤트별 값만 받는다. 이 규칙은 Extension의 처리 메서드와 구분한다.

`ExtensionRequest`가 반환한 Request는 Extension의 `__call__`과 다음 요청 훅에 전달한다. `ExtensionRequestResponse`가 반환한 Response는 이전 응답을 대체해 호출자에게 전달한다. 입력 응답이 `None`인 직접 출력 경로에서는 응답이 이미 writer로 처리되었으므로 훅도 `None`을 반환해야 하며 새 Response를 만들 수 없다. 오류 훅은 관찰 전용이며 오류를 소비하거나 응답으로 바꾸지 않는다.

## 6. 기능 요구사항

### EXT-01. 클래스 선언 기반 설정과 Factory 결과

Extension 하위 클래스는 `__init_subclass__`를 통해 다섯 이벤트별 훅을 설정할 수 있어야 한다. 키워드는 `on_startup`, `on_cleanup`, `on_request`, `on_request_response`, `on_request_error`로 한다. 각 설정은 해당 인터페이스의 단일 인스턴스 또는 해당 인터페이스 인스턴스의 시퀀스를 허용한다. 설정을 생략한 이벤트는 빈 훅 시퀀스로 처리한다. `None`, 지원하지 않는 타입 및 잘못된 시퀀스 원소는 클래스 구성 시 명시적으로 `TypeError`로 거부해야 한다.

입력 시퀀스는 등록 시점의 순서를 보존하고, 이후 호출자가 원본 시퀀스를 변경해도 등록된 훅 구성이 바뀌지 않도록 복사해야 한다. 상속 시 훅 계약을 어떻게 적용할지 공개 동작을 정의해야 한다. 요구되는 기본 동작은 부모 클래스의 설정을 상속하고, 하위 클래스가 이벤트를 명시적으로 설정하면 해당 이벤트의 상속 설정을 대체하는 것이다.

Application은 생성자에서 `ExtensionFactory` 인스턴스의 시퀀스를 받아 보관한다. 생성자에서는 Factory를 호출하지 않는다. Extension 클래스나 미리 생성된 Extension 인스턴스를 직접 등록 대상으로 받지 않는다. 호출자는 `add/load`로 일반 RequestRunner 등록을 마친 뒤 `Application.start()`를 호출한다. Application은 시작 과정에서 Factory를 등록 순서대로 호출해 Extension과 라우트 목록을 생성한다. Factory 호출 오류는 시작 오류로 호출자에게 전파한다. Factory는 Application별로 별도 Extension 인스턴스를 생성해야 한다.

Factory의 반환 계약은 `(extension: Extension, routes: Sequence[Route])`이다. 라우트가 없는 Extension은 빈 시퀀스를 반환한다. Application은 반환 시퀀스를 등록 시점에 복사하고 각 원소가 유효한 Route인지 검증해야 한다. 반환 튜플 형식, Extension 인스턴스 및 Route 원소가 계약에 맞지 않으면 시작 과정에서 명시적으로 거부한다. `routes=None`은 허용하지 않는다.

Factory가 반환한 Route 객체는 HTTP method, URL 매칭 규칙 및 라우트별 우선순위를 표현한다. Application은 기존 Route 계약에 따라 이를 등록하고 매칭한다. `FileSystemRoute`와 같은 특수 매칭은 이를 사용하는 ExtensionFactory와 라우트 타입이 제공한다. 기존 단일 `path` 및 `methods`만으로 Extension 라우트를 암묵 생성하지 않는다.

Extension 생성과 요청 실행의 Application 의존성을 분리한다. `ExtensionFactory`는 `__call__(application: Application) -> tuple[Extension, Sequence[Route]]` 계약을 가지며, Application이 Factory를 호출해 Extension과 라우트 목록을 함께 얻는다. Factory는 Application에서 필요한 구성값·라우트 메타데이터·공유 서비스 등을 조회하여 Extension 생성자에 전달할 수 있다. Extension은 전달받은 의존성만 보유하며 Application 객체를 저장하거나 요청 처리 시 전달받지 않는다. 라우트 선언을 Extension의 인스턴스 메서드로 중복 제공하지 않는다.

Extension 요청 처리 진입점은 `__call__(request: Request) -> Optional[Response]`로 한다. Factory와 Extension 추상 클래스의 공개 골격은 다음 계약으로 정의한다.

```python
class ExtensionFactory(ABC):
  @abstractmethod
  def __call__(
      self,
      application: Application,
  ) -> tuple[Extension, Sequence[Route]]:
    raise NotImplementedError


class Extension(ABC):
  def __init_subclass__(...):
    ...

  def __init__(...):
    ...

  @abstractmethod
  def __call__(self, request: Request) -> Optional[Response]:
    raise NotImplementedError
```

`Extension.__init_subclass__`는 다섯 훅의 클래스 선언 계약을 구성하고 `Extension.__init__`은 Extension별 의존성을 초기화한다. `__call__`은 Request를 처리하며 추상 메서드다. 현재 요구사항에서는 라우트가 없는 Extension도 `__call__` 구현을 제공해야 한다. `ExtensionFactory`는 Application을 받아 `(Extension, Sequence[Route])`를 반환하는 추상 `__call__`을 제공한다. 라우트가 없는 경우 빈 시퀀스를 반환한다. Extension 자체에는 `routes()` 계약을 두지 않는다. 기존 `path`, `methods`, `route()`, `routes()`, `bind()`, `start()`, `stop()`, `begin()`, `end()`는 Extension 공개 API에서 제거한다.

### EXT-02. 시작 이벤트

Application 시작 순서는 다음과 같다.

1. 호출자가 일반 RequestRunner의 `add/load`를 완료한다.
2. `Application.start()`에서 Application의 `ApplicationStartup` 훅을 실행한다.
3. Factory를 등록 순서대로 호출한다. 각 Factory가 반환한 Extension과 Route 시퀀스를 검증·등록한 뒤 해당 Extension의 `ExtensionStartup` 훅을 실행한다.
4. 모든 Factory 처리와 Extension 시작 훅이 성공하면 Application을 실행 상태로 전환한다.

Factory는 생성 시 이미 등록된 일반 RequestRunner 라우트에 접근할 수 있다. 나중에 호출될 Factory의 라우트까지 생성 시점에 등록되어 있음을 보장하지는 않는다. 전체 라우트 등 변경 가능한 정보를 사용하는 구현체는 생성 시점의 복사본과 실행 중 조회할 공유 객체를 구분해야 한다.

훅 설정은 Extension 클래스의 `__init_subclass__`에 유지하며, Factory 자체에 생명 주기 훅을 등록하거나 Factory가 시작 훅을 직접 실행하지 않는다. Application이 생성된 Extension의 훅을 실행한다. Extension은 시작 훅에서 자신이 소유한 자원을 준비하거나 백그라운드 작업을 시작할 수 있다. 기존 Extension `start(app)` 메서드는 제거하며 호출하지 않는다.

Application 시작 훅이 실패하면 Factory를 호출하지 않는다. Factory 호출, 결과 검증·등록 또는 Extension 시작 훅이 실패하면 이후 Factory 및 시작 훅을 실행하지 않고 오류를 전파한다. Application은 시작을 완료한 Extension을 역순으로 방문해 각 Extension의 `ExtensionCleanup` 훅을 실행하고 원래 시작 오류를 전파한다. 시작 실패로 추가된 Extension 라우트는 롤백하며 일반 RequestRunner 등록은 보존한다. 시작에 실패한 Extension은 시작 완료로 간주하지 않으며, 실패한 Factory·생성자·시작 훅이 자체적으로 만든 부분 자원의 롤백은 해당 구현의 책임이다.

### EXT-03. 정리 이벤트

Application 종료 순서는 Extension을 등록 역순으로 방문해 각 Extension의 `ExtensionCleanup` 훅을 실행한 뒤 Application의 `ApplicationCleanup` 훅을 실행하는 것이다. 각 Extension 내부의 훅은 등록 순서대로 실행한다. Extension은 정리 훅에서 자체 백그라운드 작업을 중지하고 해당 작업이 소유한 자원을 정리해야 한다. 정리 훅이 끝난 뒤에도 Extension이 시작한 작업이 무기한 실행 상태로 남아서는 안 된다. 기존 Extension `stop(app)` 메서드는 제거하며 호출하지 않는다. 한 Extension의 정리 실패가 다른 Extension의 정리를 막아서는 안 되며, 전체 정리 시도 후 Application 정리 정책에 따라 첫 오류를 호출자에게 전파하고 후속 오류를 기록해야 한다.

한 Extension의 정리 훅이 실패하면 그 Extension 안의 후속 정리 훅은 실행하지 않고 오류를 전파한다. Application은 나머지 Extension의 정리와 Application 정리 훅을 계속 시도한다. Extension이 시작되지 않았거나 Application이 이미 실행 중이 아닌 경우 기존 동작을 보존하여 정리 훅을 실행하지 않는다.

### EXT-04. 요청 이벤트 경계

`ExtensionRequest`, `ExtensionRequestResponse`, `ExtensionRequestError`는 해당 Extension의 라우트가 실제로 선택되어 Extension의 `__call__` 처리를 수행하는 경우에만 실행한다. 일반 요청, 다른 Extension의 요청, 라우트 선택 실패 및 Extension의 `__call__`에 도달하기 전 발생한 내부 RequestRunner의 검증·필터 오류는 Extension 요청 훅의 대상이 아니다.

요청 성공 경로는 다음과 같다.

1. 내부 RequestRunner가 Extension의 `__call__`을 호출하기 직전에 `ExtensionRequest` 훅을 등록 순서대로 실행한다.
2. 각 훅이 반환한 Request를 다음 훅 및 Extension의 `__call__`에 전달한다.
3. Extension의 `__call__`이 정상 반환하면 `ExtensionRequestResponse` 훅을 등록 순서대로 실행한다.
4. 각 응답 훅의 반환값을 다음 응답 훅과 Extension 처리 호출자에게 전달한다.

Extension의 요청 처리 또는 해당 Extension 요청 훅에서 예외가 발생하면 `ExtensionRequestError` 훅을 등록 순서대로 실행한 뒤 요청 오류를 호출자에게 전파한다. 오류 훅은 원래 오류를 소비하거나 성공 응답으로 변환하지 않는다. 오류 훅 자체가 실패하면 훅 오류를 전파하고 원래 처리 오류도 예외 체인에 보존해야 한다. Request 훅 또는 Response 훅의 실패는 정상 요청 완료로 취급하지 않는다.

요청 훅의 반환은 Extension 처리 결과에만 적용된다. 훅은 Application 라우팅을 변경하거나 실제 응답 전송·스트림 소비·연결 종료를 제어하지 않는다. Extension 훅은 Application이 선택한 라우트가 해당 Extension에 속할 때 `RunExtension` 처리 경계에서 실행한다.

### EXT-05. 기존 확장점 제거 및 책임 이전

- `bind(app)`, `start(app)`, `stop(app)`, `begin(request)`, `end(request, context, status, error)`를 Extension의 공개 확장점에서 제거한다.
- Application은 `ExtensionFactory` 시퀀스를 보관했다가 `start()`에서 등록 순서대로 각 Factory를 `factory(application)` 형태로 호출한다. Factory는 Extension 인스턴스와 Route 시퀀스를 반환하며 필요한 Application 소유 데이터를 Extension 생성자에 전달한다. Extension 인스턴스는 Application 참조를 보유하지 않는다.
- Application은 Factory 결과의 Route 시퀀스를 검증해 Router에 등록한다. Route와 Extension 처리기의 연결은 구현체 책임이며, Extension 하위 클래스의 사용자 정의 `bind(app)` 동작은 지원하지 않는다.
- `route(method, handler)` 단일 라우트 생성 편의 메서드와 Extension의 단일 기본 경로·메서드 목록 기반 자동 라우트 생성은 제거한다. 다중 라우트와 특수 매칭은 Factory가 반환하는 라우트 객체에 표현한다.
- Extension의 `__call__`은 `__call__(request)` 계약을 사용한다. `RunExtension`은 요청만 처리 메서드에 전달한다. Application은 Factory에만 전달하며 Extension 훅 인자나 Extension 요청 처리 인자로 전달하지 않는다.
- Extension별 요청 관찰은 Application의 `ApplicationRequest`, `ApplicationRequestResponse`, `ApplicationRequestError` 훅으로 옮긴다. 해당 훅은 Extension 라우트 여부와 무관하게 Application 처리 경계에서 실행된다.
- Application 훅은 요청 생성 전이나 Application 처리 반환 후의 서버 전송 과정을 관찰하지 않는다. 기존 `end`가 제공하던 응답 전송 완료 후 정리 및 전송 중 오류 관찰은 이전하지 않는다. `ApplicationRequestResponse`는 Application이 응답을 반환할 때 실행되며 실제 전송 완료를 의미하지 않는다.
- `onRequest`와 `onResponse`는 기존 내부 RequestRunner 필터 계약을 유지한다. 새 Extension 훅과 필터의 호출 위치·오류 경계가 겹치지 않도록 테스트한다.
- Application 훅과 RequestRunner 훅은 각각의 책임 경계에서 실행한다. Extension 훅을 다른 Extension이나 내부 RequestRunner의 훅 이벤트로 중복 실행해서는 안 된다.

### EXT-06. 다중 훅과 오류 정책

모든 이벤트의 복수 훅은 등록 순서대로 실행한다. 시작·요청·응답·오류 이벤트에서 한 훅이 실패하면 같은 이벤트의 나머지 훅을 건너뛰고 오류를 전파한다. 정리 이벤트는 같은 Extension 안에서는 이 정책을 따르며, Extension 간 정리는 EXT-03에 따라 계속 시도한다.

훅 오류를 조용히 무시하거나 임의의 Request·Response·성공 상태로 대체해서는 안 된다. 원래 요청 오류와 오류 훅 오류가 함께 발생하면 원래 오류를 예외 체인에서 보존해야 한다.

### EXT-07. HTTP 라우트가 없는 Extension과 백그라운드 작업

Extension은 HTTP 라우트를 제공하지 않아도 유효하다. Factory가 빈 라우트 시퀀스를 반환하면 Application은 해당 Extension에 대한 라우트를 등록하지 않지만, Extension의 시작·정리 훅은 다른 Extension과 동일하게 Application 수명 주기 순서에 따라 실행해야 한다.

이 계약을 통해 Extension은 시작 훅에서 파일 정리나 주기적 데이터 기록과 같은 자체 작업을 시작하고, 정리 훅에서 작업을 중지하고 자원을 정리할 수 있다. 프레임워크는 스레드·스케줄러를 자동 생성하거나 주기적 실행 주기를 제공하지 않는다. 백그라운드 작업의 생성, 동기화, 실패 보고 및 종료는 Extension이 소유하며, 정리 훅은 작업 종료를 요청하고 필요한 대기를 수행해야 한다.

현재 계약에서는 라우트가 없는 Extension도 추상 메서드인 `__call__(request)`를 구현해야 한다. 해당 메서드는 이 Extension에 라우트가 등록되지 않는 동안 호출되지 않는다. 라우트가 없는 Extension을 위한 `__call__` 생략 지원 여부는 별도 결정 전까지 추가하지 않는다.

## 7. 비기능 요구사항 및 제외 범위

- 훅을 설정하지 않은 Extension은 기존 라우트 등록, 실행 및 RequestRunner 필터 동작을 유지해야 한다.
- Application은 Factory가 반환한 등록 당시 라우트 목록을 사용한다. 이후 목록을 변경해도 이미 등록된 Application의 라우트가 묵시적으로 변경되지는 않는다.
- Factory는 하나 이상의 Route 객체 또는 빈 라우트 시퀀스를 반환할 수 있다. 같은 method·URL이 다른 처리 대상으로 중복 등록되면 시작 오류로 명시적으로 거부한다.
- 라우트가 없는 Extension도 Application에 등록할 수 있으며, HTTP 요청 훅은 호출되지 않더라도 시작·정리 훅은 Application 수명에 맞춰 실행한다.
- 기존 `path`, `methods`, `route(method, handler)`를 사용하는 Extension은 Factory가 반환하는 Route 시퀀스로 이전해야 한다. 특수 매칭 동작은 Extension 소유의 Route 구현으로 옮긴다.
- 클래스에 설정된 훅 인스턴스는 동일 Extension 클래스의 인스턴스 사이에서 공유될 수 있다. 훅 구현의 가변 상태 동기화는 사용자 책임이며, 프레임워크는 임의로 잠금이나 프로세스 간 상태 공유를 제공하지 않는다.
- 훅은 Extension의 Application 등록 순서 및 요청 처리 순서에 맞춰 실행되어야 하며, 등록 순서가 불명확한 입력은 허용하지 않는다.
- `bind/start/stop/begin/end`를 직접 오버라이드하던 사용 코드는 호환되지 않는다. 기존 Extension 요청 관찰 중 Application 처리 경계에 속한 동작은 Application 훅으로 옮길 수 있으나, 요청 생성 전과 응답 전송 과정 및 전송 후 정리 시점은 제공되지 않는다.
- Extension 훅은 Application 생성·전역 디스패치, 일반 RequestRunner 내부 검증·실행, HTTP 연결 및 응답 전송의 생명 주기를 포함하지 않는다.
- 새 Extension 요청 훅은 해당 Extension 라우트 처리에만 적용한다. 모든 요청의 관찰은 Application 훅의 책임이다. Extension 시작·정리 훅은 라우트 유무와 무관하게 실행된다.

## 8. 수용 기준

| ID | 검증 기준 |
| --- | --- |
| AC-01 | 다섯 Extension 훅 인터페이스와 입력·반환 계약이 표와 일치하고, 공개 API에서 사용할 수 있다. |
| AC-02 | 하위 클래스 선언에서 단일·복수 훅을 설정할 수 있으며 잘못된 타입과 원소를 명시적으로 거부한다. |
| AC-03 | 부모 훅의 상속, 하위 클래스의 명시적 재설정, 복수 훅의 등록 순서가 테스트로 검증된다. |
| AC-04 | Factory가 유효한 Route 시퀀스 또는 빈 시퀀스를 반환하고, Application이 이를 검증해 Router에 등록한다. |
| AC-05 | Route의 기존 매칭 계약에 따라 여러 경로·메서드와 특수 매칭이 올바르게 처리되고 Extension 요청 처리기로 연결된다. |
| AC-06 | Application이 ExtensionFactory 인스턴스만 받아 순서대로 호출하고, 각 Factory가 Application마다 Extension 및 Route 시퀀스를 반환한다. ExtensionFactory 추상 클래스는 Application 입력·반환 계약을, Extension 추상 클래스는 `__init_subclass__`, `__init__`, Request만 받는 추상 `__call__`을 제공한다. |
| AC-07 | Application 생성 시 Factory는 호출되지 않고, 일반 RequestRunner 등록 후 `start()`에서 Application 시작 훅 → Factory 호출·결과 등록 → 해당 Extension 시작 훅 순서로 실행된다. 종료 시 Extension 정리 훅 다음에 Application 정리 훅이 실행된다. |
| AC-08 | Factory에 Application이 전달되어 생성된 Extension의 `__call__(request)`에는 Request만 전달되고, 요청·응답 변환, 직접 출력의 `None` 계약 및 오류 훅이 검증된다. |
| AC-09 | 라우트 선택 실패에서는 Extension 요청 훅이 호출되지 않고, 오류 훅 실패 시 원래 예외가 보존된다. |
| AC-10 | 라우트가 없는 Extension에 대해 Factory가 빈 시퀀스를 반환해도 등록 가능하고, 해당 Extension의 시작·정리 훅이 정상 실행된다. |
| AC-11 | 기존 RequestRunner 필터 및 Application 훅과 중복 실행이 없고, 서버 전송 과정 관찰 범위와 훅 미설정 Extension 동작이 명세대로 검증된다. |
| AC-12 | Factory 호출·결과 등록·Extension 시작 실패 시 이후 시작 처리를 중단하고, 시작 완료 Extension을 역순 정리하며 추가된 Extension 라우트를 롤백한다. 일반 RequestRunner 등록과 원래 시작 오류는 보존된다. |

## 9. 구현 적용 기준

구현은 Application의 다섯 훅 이벤트 의미와 오류 처리 원칙을 기준으로 Extension 전용 인터페이스를 제공한다. 설정은 상위 명세대로 Extension 클래스 선언에서 받으며, Factory 자체에는 훅을 설정하지 않는다. Extension 요청 훅은 해당 Extension 라우트 처리 경계에서 실행한다. Application은 생성자에서 보관한 `ExtensionFactory`를 `start()`에서 Application 시작 훅 실행 후 호출해 `(Extension, Sequence[Route])`를 받는다. 각 Factory 결과를 검증·등록한 뒤 생성된 Extension의 시작 훅을 실행한다. Factory가 필요한 의존성을 Extension 생성자에 전달하며, Extension 요청 처리 시그니처는 `__call__(request)`로 한다. Extension 자체에는 `routes()`를 두지 않는다.

기존 `path`, `methods`, `route`, `routes`, `bind`, `start`, `stop`, `begin`, `end` Extension 멤버와 단일 경로 자동 등록 구조는 제거한다. Extension 생성은 Application이 등록된 Factory를 호출해 수행하며, Factory에서 Application 소유 값 중 Extension에 필요한 의존성만 생성자에 전달한다. Factory는 Extension과 `Sequence[Route]`를 함께 반환하며 라우트가 없는 경우 빈 시퀀스를 반환한다. Extension 인스턴스의 요청 처리 및 훅은 Application 참조를 받지 않는다. Application 처리 경계의 요청 관찰만 Application 요청 훅으로 이전하며, 요청 생성 전이나 실제 응답 전송 중·후의 관찰 및 정리는 이전하지 않는다. 내부 RequestRunner 필터의 계약은 유지한다. FileSystem 같은 확장 고유 매칭은 Factory가 반환하는 Route 구현으로 제공한다. Route와 Extension 처리기의 연결은 구현체에서 Route 계약에 맞게 구현한다. HTTP 라우트가 없는 Extension의 시작·정리 훅을 통한 자원 및 백그라운드 작업 수명 관리도 검증한다. 공개 인터페이스를 패키지 API에 추가하고, 정상·오류·직접 출력 경로, 라우트 수집·매칭, 상속·다중 훅, Extension/Application/RequestRunner 간 호출 순서를 각각 테스트한다.
