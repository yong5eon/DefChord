# Extension 생명 주기 훅 요구사항 명세서

## 1. 목적과 현재 상태

[Extension 이슈](./ISSUE.md)의 최신 설계를 정의한다. Factory 방식으로 구현한 뒤 사용 코드의 조립 부담을 검토하여, 생성된 Extension을 등록하고 시작 단계에서 연결하는 구조로 변경한다.

이 문서의 인스턴스 등록·생성자 훅·시작 단계 연결 계약을 Python 구현과 기본 확장·샘플에 반영했다. 새 계약의 검증 결과는 [구현 계획의 검증 기록](./PLAN.md#7-검증-기록)에 기록한다.

근거:

- [상위 공통 명세](../2/REQUIREMENTS.md)
- [Application 훅 명세](../4/REQUIREMENTS.md)
- [구현 계획](./PLAN.md)
- [Application](../../../src/Application.py), [Extension](../../../src/Extension.py)
- [Extension 실행기](../../../src/Runners/RunExtension.py), [시작 배너](../../../src/Startup.py)
- [샘플](../../../samples/Sample.py)

## 2. 확정한 구조

| 항목 | 계약 |
| --- | --- |
| Application 등록 대상 | 호출자가 생성한 Extension 인스턴스의 시퀀스 |
| Extension 생성자 | 설정과 다섯 이벤트별 사용자 훅을 입력받음 |
| Application 연결 | `startup(application)` |
| 라우트 등록 | Extension의 `startup(application)`에서 Application의 등록 경로를 사용 |
| 요청 처리 | 추상 `__call__(request) -> Optional[Response]` |
| 정리 | `cleanup()` |
| 불필요해진 공개 계약 | `ExtensionFactory`, 별도 `bind()`, `route()`, `routes()` |
| Extension 요청·응답 필터 | RequestFilter·ResponseFilter를 사용하지 않고 Extension 훅으로 대체 |
| 시작 배너 | 시작 전에 로고와 일반 라우트, `str(extension)`으로 얻은 확장 표시값·개수를 출력 |

Extension은 Application 참조를 보관할 수 있다. Application 참조를 제거하기 위한 Factory, 조회 함수 묶음 또는 별도의 범용 Context를 강제하지 않는다. Application은 요청 메서드나 사용자 훅의 인자로 매번 전달하지 않는다.

HTTP 라우트 없이 파일 정리·주기 작업 등의 자원을 관리하는 Extension도 허용한다. 요청 메서드는 계속 추상 계약으로 유지하며, 자동 스케줄러나 스레드 실행 기능을 프레임워크에 추가하지 않는다.

## 3. 생성자와 공개 훅 계약

훅은 Extension의 `__init_subclass__`가 아니라 인스턴스 생성자에서 설정한다. 구현체는 아래 키워드를 받아 부모 생성자에 전달한다.

| 생성자 인자 | 인터페이스 | 훅 입력 | 반환 |
| --- | --- | --- | --- |
| `on_startup` | `ExtensionStartup` | 없음 | `None` |
| `on_cleanup` | `ExtensionCleanup` | 없음 | `None` |
| `on_request` | `ExtensionRequest` | `Request` | `Request` |
| `on_request_response` | `ExtensionRequestResponse` | `Request`, `Optional[Response]` | `Optional[Response]` |
| `on_request_error` | `ExtensionRequestError` | `Request`, `Exception` | `None` |

- 인자를 생략하거나 `None`이면 해당 이벤트의 사용자 훅이 없다. 구현체 예시에 제시한 `None` 기본값을 허용한다.
- 단일 인터페이스 인스턴스 또는 해당 인터페이스 인스턴스의 시퀀스를 받는다. 복수 훅은 입력 순서대로 실행한다.
- 시퀀스는 튜플로 복사하고 잘못된 타입·문자열·원소는 구성 시 `TypeError`로 거부한다.
- 인스턴스별로 구성하며 이전 클래스 선언 기반 훅 상속·대체 계약은 제거한다.
- 공개 이름은 `on_request_response`, `on_request_error`로 통일한다. `on_response`, `on_error`, `onRequest`, `onResponse`를 별도 별칭으로 추가하지 않는다.
- 사용자 훅은 Application 또는 Extension을 추가 인자로 받지 않는다. `startup(application)`은 구현체의 수명 메서드이며 인자 없는 사용자 시작 훅과 구분한다.

공개 골격은 다음과 같다. 아래는 시그니처를 보여주는 개요이며 실제 훅 실행과 입력 검증은 구현해야 한다.

```python
class Extension(ABC):
  def __init__(
    self,
    *,
    on_startup=None,
    on_request=None,
    on_request_response=None,
    on_request_error=None,
    on_cleanup=None,
  ):
    ...

  def startup(self, application) -> None:
    ...

  def cleanup(self) -> None:
    ...

  def __str__(self) -> str:
    return type(self).__name__

  @abstractmethod
  def __call__(self, request) -> Optional[Response]:
    raise NotImplementedError
```

## 4. 시작·등록과 Application 의존성

### EXT-01. 구성과 시작 순서

1. 호출자가 Extension을 생성하고 `Application(exts=(...))`에 전달한다.
2. Application은 등록 시 인스턴스를 검증하고 입력 시퀀스를 복사한다. 생성자에서는 Extension을 시작하지 않는다.
3. 호출자가 일반 RequestRunner를 `add/load`로 등록한다.
4. 서버는 바인딩 성공 후 로고와 등록된 구성 정보를 출력한다.
5. `Application.start()`는 Application 시작 훅을 실행한다.
6. 등록 순서대로 `extension.startup(application)`을 호출한다.
7. 모든 시작이 성공하면 실행 상태로 전환하고 요청을 수신한다.

각 Extension의 `startup(application)`은 필요한 Application 참조 연결, 라우트 등록 및 자원 준비를 처리한다. 구현체는 필요한 준비를 끝낸 뒤 `super().startup(application)`을 호출하여 생성자에 등록된 사용자 시작 훅을 실행한다. 시작 단계에서 사용자 훅이 중복 실행되지 않아야 한다.

Application 전체 시작 훅이 Extension 시작보다 먼저 실행된다는 기존 순서는 유지한다. 그러므로 그 시점에 Extension 라우트가 등록되어 있다고 가정하지 않는다.

### EXT-02. 라우트 등록 책임

- Extension이 등록할 Route와 요청 처리기의 연결을 결정하고 Application이 검증·등록·매칭·소유 관계를 관리한다.
- Extension은 Application의 등록 경로를 사용한다. 라우터 내부 목록을 직접 수정하는 사용 방식을 요구하지 않는다.
- 등록 경로는 `startup()` 중 호출할 수 있어야 하며, 일반 RequestRunner의 실행 중 등록 금지는 유지한다.
- 여러 경로·메서드 및 라우트 없는 Extension을 허용한다. 공통 `path/methods` 속성을 베이스 계약이나 배너 출력 조건으로 강제하지 않는다.
- FileSystemRoute는 FileSystem 확장 모듈에 두며 접두 경로 매칭, 디코딩, 파라미터와 우선순위는 보존한다. Specifications는 해당 모듈에서 가져와 문서 경로를 변환한다.
- 먼저 시작하는 Extension은 뒤 Extension의 라우트 등록 완료를 보장받지 않는다. Specifications·Metrics 등은 실행 중 현재 라우팅 정보를 조회하고 불완전한 시작 시점의 복사본을 고정하지 않는다.

### EXT-03. 시작 실패

Application 시작 훅이 실패하면 Extension을 시작하지 않는다. Extension 시작·라우트 등록·사용자 시작 훅이 실패하면 이후 Extension을 시작하지 않고, 시작 완료 Extension을 역순 정리한 뒤 최초 시작 오류를 전파한다. 롤백 중 정리 오류는 기록하되 원래 오류를 대체하지 않는다.

실패한 Extension의 부분 자원 정리는 해당 구현체가 책임진다. Application은 이번 시작에 추가된 Extension 라우트를 부분 등록분까지 롤백하고 일반 라우트는 보존한다. 이 경로에서 Application 정리 훅을 호출하지 않는 기존 정책은 유지한다.

### EXT-04. 정리와 재시작

Application 종료 시 실행 상태를 먼저 해제하고 시작 완료 Extension의 `cleanup()`을 등록 역순으로 호출한 뒤 Application 정리 훅을 실행한다. 각 이벤트의 복수 사용자 훅은 등록 순서대로 실행하며 같은 이벤트의 훅 실패 시 후속 훅은 중단한다.

한 Extension의 정리 실패가 다른 Extension 및 Application 정리를 막아서는 안 된다. 모든 정리를 시도한 뒤 첫 오류를 전파하고 후속 오류를 기록한다. 사용자 정리 훅 실패 때문에 구현체 자원 회수가 누락되지 않도록 구현한다. 백그라운드 작업은 종료 신호와 필요한 대기까지 완료해야 한다.

실행 중 중복 시작은 거부하고 이미 정지한 Application의 `stop()`은 아무 훅도 호출하지 않는다. 재시작 시에는 전달받은 동일 Extension 인스턴스를 다시 시작하며 상태·자원과 라우트를 재설정하여 중복 등록을 방지한다. 동일 인스턴스의 여러 Application 공유는 거부한다.

## 5. 요청 처리와 기존 필터 제거

### EXT-05. Extension 요청 경계

실제로 Extension 처리에 진입할 때 요청 훅 → `extension(request)` → 응답 훅 순서로 실행한다. 요청 훅의 반환 Request는 다음 훅과 요청 메서드에 전달하고 응답 훅은 현재 응답을 반환값으로 교체할 수 있다.

직접 출력의 입력 응답이 `None`이면 응답 훅도 `None`을 반환해야 한다. 일반 응답을 버리고 직접 출력 없이 `None`만 반환하는 동작은 오류다. 교체되거나 실패한 응답의 본문 자원도 정리한다.

요청·응답 훅 또는 Extension 처리 오류는 Extension 오류 훅을 실행한 뒤 전파한다. 오류 훅은 관찰 전용이다. 오류 훅 자체가 실패하면 원래 처리 오류를 예외 체인에 남긴다. 라우팅 실패·일반 핸들러·다른 Extension 및 Extension 처리 진입 전의 검증 오류는 해당 Extension 훅의 대상이 아니다.

Application 요청 훅은 이 경계의 바깥에서 동작한다. 응답 반환 이후 서버 전송·스트림 소비 실패를 종료된 Extension 요청 경계에 다시 통지하지 않는다.

### EXT-06. FileSystem과 기본 Extension 이전

후속 [feature/6 명세](../6/REQUIREMENTS.md)에서 일반 RequestRunner 필터도 제거하고 세 훅으로 대체한다. 내부 RequestRunner에 응답 훅이 설정된 직접 출력은 writer의 begin 또는 upgrade에서 해당 훅을 먼저 실행한 뒤, 확장 처리 완료 시 Extension 응답 훅을 실행한다. 반환 응답은 기존처럼 Extension 응답 훅 이후 RequestRunner 응답 훅 순서다. RequestRunner 콜백을 통한 직접 출력 후처리 실패는 실행 중인 Extension 경계에도 전파되며, 응답 훅 완료를 전체 처리 성공으로 보지 않는다.

FileSystem의 기존 `onRequest/onResponse`는 새 Extension 생성자의 `on_request/on_request_response`로 대체한다. 기본 File을 비롯한 Extension에서도 RequestFilter·ResponseFilter 인자를 받거나 내부 RequestRunner 필터에 연결하지 않는다.

새 요청 훅은 Request만 반환하며 `(request, response)` 조기 응답 튜플을 반환하지 않는다. 샘플의 파일명 변환과 응답 교체도 새 Extension 훅 인터페이스로 이전한다. RequestRunner 자체의 기존 필터 API 제거는 별도 작업으로 남겨두며 이번 변경에서 일반 핸들러의 계약은 깨지 않는다.

### EXT-07. Metrics의 전체 요청 관찰

Extension 요청 훅은 해당 Extension 요청에만 적용된다. 이를 Metrics의 전체 요청 수집으로 확대하거나 모든 Extension 훅을 모든 요청에 호출하지 않는다. 전체 요청 관찰 경계는 Application 요청 훅이며 처리 완료와 응답 전송 완료는 구분한다.

사용자 결정에 따라 Metrics는 시작 단계에서 명시적인 Application 훅 등록·해제 API를 사용한다. `Metrics('/metrics')` 등록만으로 전체 요청 수집을 연결하며 수집기와 세 Application 훅을 사용자가 수동 조립하지 않는다.

- `Application.add_request_hooks(on_request=..., on_request_response=..., on_request_error=...)`는 현재 시작 중인 Extension 소유로 등록하고 해제 토큰을 반환한다. 입력은 기존 Application의 이벤트별 인터페이스 인스턴스 또는 시퀀스이며 None은 허용하지 않는다.
- `remove_request_hooks(token)`은 소유 Extension의 시작·정리 단계에서만 허용한다. 잘못된 토큰·다른 소유자·중복 해제는 오류다.
- 등록 훅은 등록 순서대로, Application 생성자 훅보다 먼저 실행한다. 기존 생성자 훅 튜플은 수정하지 않는다.
- 같은 이벤트에서 동일 훅 인스턴스의 중복 입력·기존 동적 등록·생성자 등록과의 중복은 `ValueError`로 거부한다. 빈 묶음 등록도 오류다.
- 시작 실패 시 실패 Extension의 등록분까지 롤백한다. 정리 오류가 발생해도 Application이 해당 Extension 소유 등록을 제거하고 재시작 중복을 방지한다.
- 요청마다 등록 구성을 복사하여 진입·정상·오류 경계에서 일관되게 사용한다. 실행 중 등록·해제는 허용하지 않는다.
- 수집기의 동시 요청 격리·Request 교체와 중첩 호출·후속 응답 훅 오류의 실패 재분류를 유지한다.

## 6. 로고와 구성 정보

- 프레임워크가 관리하는 시작 로그보다 로고가 먼저 출력되어야 한다. 로고 출력 때문에 Extension을 미리 시작하지 않는다.
- 시작 전 배너는 일반 등록 라우트와 이미 생성된 Extension의 개수 및 `str(extension)` 결과를 출력한다. 배너는 확장별 표시 문자열의 내용을 직접 조립하지 않는다.
- 표시 진입점은 `__str__()`로 통일한다. 베이스의 기본 구현은 클래스 이름을 반환하며, 구현체는 `__str__()`을 재정의해 경로 등 필요한 구성 정보를 포함할 수 있다. `__repr__()`은 디버깅 표현으로 별도 구현할 수 있으나 배너가 두 메서드 사이를 임의로 선택하지 않는다.
- 표시 문자열은 생성자에서 받은 설정만으로 시작 전에 만들 수 있어야 한다. 라우트 등록·자원 연결·훅 실행 등의 부수 효과를 발생시키지 않으며 비밀 값은 포함하지 않는다.
- 배너는 Extension 라우트 목록이나 공통 `path/methods` 속성을 조회하지 않는다. 구현체가 자신의 경로를 표시하는 것은 허용하며 라우트 없는 Extension도 동일한 방식으로 표시한다.
- 이 배너는 시작 성공을 보증하는 메시지가 아니라 등록된 구성의 안내다. 시작 실패 시 정상 서비스 중이라고 표시하지 않는다.
- 사용자 코드가 서버 시작 전 직접 출력하는 로그까지 순서를 제어하는 것은 범위 밖이다.

## 7. 수용 기준

| ID | 확인할 결과 |
| --- | --- |
| AC-01 | 생성된 Extension 등록, Factory 및 클래스 기반 훅 설정 제거 |
| AC-02 | 생성자 훅의 단일·복수·None·잘못된 입력 검증과 시퀀스 복사 |
| AC-03 | `startup(application)`에서 의존성 연결·라우트 등록·자원 준비 후 사용자 시작 훅 실행 |
| AC-04 | 일반·다중·특수·빈 라우트 및 소유 관계, 충돌 검증 |
| AC-05 | 시작 실패 시 후속 중단·완료 Extension 역순 정리·라우트 롤백 |
| AC-06 | 종료의 역순 정리·오류 전파·자원 회수·재시작 중복 방지·소유권 |
| AC-07 | 요청 변환·응답 교체·오류 훅·직접 출력의 올바른 실행과 정리 |
| AC-08 | Extension에서 RequestFilter·ResponseFilter 제거, 일반 RequestRunner 계약 보존 |
| AC-09 | 로고가 시작 로그보다 먼저 나오고 확장 개수·기본 및 재정의된 `str(extension)`을 시작 전 라우트 조회 없이 표시 |
| AC-10 | 기본 Extension·샘플·명세 스크립트 이전 및 라이브 라우트 조회 |
| AC-11 | Metrics 전체 요청 관찰과 Extension 요청 경계를 구분하고 연결 계약을 명시 |
| AC-12 | 서버 수명·전송 오류·동시 요청·Application 간 상태 격리 회귀 검증 |
