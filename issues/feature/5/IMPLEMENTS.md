# Extension 생명 주기 훅 구현 기록

## 개요

[요구사항 명세서](./REQUIREMENTS.md)와 [구현 계획서](./PLAN.md)에 따라 Extension을 인스턴스 등록·생성자 훅·시작 단계 연결 구조로 변경했다. 상위 [공통 요구사항](../2/REQUIREMENTS.md)과 [Application 훅](../4/REQUIREMENTS.md)을 바탕으로, Extension 수명과 요청 경계의 책임을 구분했다.

중간에 검토·구현했던 공개 Factory 방식은 최종 계약이 아니다. 최종 구조에서는 호출자가 확장을 생성하고 Application에 전달하며, 각 확장이 시작 단계에서 필요한 라우트와 자원을 준비한다.

## 공개 계약

### 등록과 생성자 훅

`Application(exts=...)`는 Extension 인스턴스 시퀀스를 받아 튜플로 보관한다. 클래스·Factory·잘못된 원소와 동일 인스턴스 중복 등록을 거부하고, 하나의 인스턴스를 서로 다른 Application에 공유하지 못하도록 소유권을 검증한다.

Extension 생성자는 다음 키워드 전용 훅을 받는다.

| 인자 | 인터페이스 | 입력 | 반환 |
| --- | --- | --- | --- |
| `on_startup` | `ExtensionStartup` | 없음 | `None` |
| `on_cleanup` | `ExtensionCleanup` | 없음 | `None` |
| `on_request` | `ExtensionRequest` | `Request` | `Request` |
| `on_request_response` | `ExtensionRequestResponse` | `Request`, `Optional[Response]` | `Optional[Response]` |
| `on_request_error` | `ExtensionRequestError` | `Request`, `Exception` | `None` |

각 값은 해당 인터페이스의 단일 인스턴스·시퀀스·None을 허용한다. 생략하거나 None이면 빈 훅이며 시퀀스는 튜플로 복사한다. 잘못된 입력은 `TypeError`로 거부한다. 클래스 선언의 훅 설정·상속 계약과 `onRequest/onResponse` 별칭은 제공하지 않는다.

### 수명과 요청 처리

- `startup(application)`은 Application 연결, 라우트 등록, 자원 준비를 담당한다. 구현체는 준비 후 `super().startup(application)`으로 인자 없는 사용자 시작 훅을 실행한다.
- 추상 `__call__(request)`는 요청만 받아 `Optional[Response]`를 반환한다. Application을 요청마다 추가 인자로 전달하지 않는다.
- `cleanup()`은 사용자 정리 훅과 구현체의 자원 회수를 담당한다. 사용자 훅 실패가 자원 회수를 막지 않도록 구현체가 보장한다.
- 기본 `__str__()`은 클래스 이름을 반환한다. 구현체는 시작 전에 알 수 있는 경로·연결 정보 등을 표현할 수 있다.
- 별도 공개 Factory·`bind/route/routes` 계약은 두지 않는다. Application 참조를 구현체가 직접 보관하는 것은 허용한다.
- HTTP 라우트가 없는 확장도 허용하지만 스레드·스케줄러를 자동으로 생성하지 않는다.

## Application 연결과 실패 정책

### 시작·종료·재시작

시작 순서는 Application 시작 훅 → 등록 순 Extension 시작 → 실행 상태 전환이다. 종료는 시작 완료 Extension의 역순 `cleanup()` → Application 정리 훅 순서다.

시작 실패 시 후속 확장은 시작하지 않고, 시작 완료 확장을 역순 정리한다. 부분 등록된 확장 라우트와 동적 요청 훅은 롤백하며 일반 라우트와 원래 등록 인스턴스 목록은 보존한다. 롤백 중 정리 오류는 기록하고 최초 시작 오류를 전파한다.

시작에 실패한 확장 자체의 부분 자원 회수는 해당 `startup()` 구현의 책임이다. Application이 실패 확장에 `cleanup()`을 다시 호출하는 구조가 아니다. FileSystem은 연결·사용자 시작 훅 실패 시 연결을 닫고, 연결 해제까지 실패해도 최초 시작 오류를 보존한다.

종료 시 확장 하나의 정리가 실패해도 나머지 확장과 Application 정리를 시도하고 첫 오류를 전파한다. 종료된 Application의 `stop()`은 추가 작업을 하지 않는다. 재시작은 동일한 등록 인스턴스를 다시 사용하고 시작 시 이전 확장 라우트를 제거한 뒤 재등록한다. 종료 직후 라우트 목록을 비우는 동작으로 바꾸지는 않았다.

### 라우트 등록

`Application.add_extension_route(extension, route)`는 현재 시작 중인 소유 확장에서만 호출할 수 있다. Route와 구체 RequestRunner 클래스를 검증하며 동일 method·URL 충돌은 거부한다.

내부 `RunExtensionFactory`는 Route에 연결할 RequestRunner 클래스를 만드는 어댑터 생성기로 유지한다. 제거한 공개 Extension 생성 Factory와 역할이 다르다.

`FileSystemRoute`는 [FileSystem 모듈](../../../src/Extensions/FileSystem.py)로 이관했다. URL 접두사 아래의 하위 경로 매칭·디코딩과 일반 라우트 우선·긴 접두사 우선 규칙은 유지한다. Specifications도 해당 모듈에서 타입을 가져와 문서 경로를 변환한다.

## 요청 경계와 전체 요청 관찰

### Extension 요청 훅

[Extension 실행기](../../../src/Runners/RunExtension.py)는 요청 훅 → 확장 호출 → 응답 훅을 실행하고, 실패 시 오류 훅을 호출한다. Request 교체·응답 교체·반환 타입 검증과 교체되거나 실패한 응답 본문의 정리를 유지했다. 오류 훅 실패 시에도 예외 맥락을 보존한다.

직접 출력 경로에서는 응답이 None이며 새 Response로 대체할 수 없다. 일반 응답을 응답 훅에서 None으로 버리는 것도 오류다.

Extension 어댑터의 RequestFilter·ResponseFilter 연결은 제거했다. FileSystem의 요청 훅은 Request를 반환하며, 기존 필터의 튜플·조기 응답 반환 계약은 사용하지 않는다. 일반 RequestRunner의 필터는 후속 정리 범위이므로 유지했다.

### 동적 Application 요청 훅

Metrics의 전체 요청 관찰을 위해 명시적인 등록·해제 API를 추가했다.

- `add_request_hooks(...)`는 확장 시작 중 이벤트별 Application 훅을 등록하고 `RequestHookRegistration` 토큰을 반환한다.
- `remove_request_hooks(token)`은 소유 확장의 시작·정리 중에만 허용한다.
- 빈 묶음, 같은 이벤트의 동일 훅 인스턴스 중복, 잘못된 토큰·다른 소유자·중복 해제는 명시적으로 거부한다.
- 동적 훅은 등록 순서대로 실행되고 Application 생성자 훅보다 앞선다. 생성자 훅 튜플을 변경하지 않는다.
- Application은 시작 실패 시 등록을 롤백하고, 정리 오류가 있어도 해당 확장 소유 등록을 제거한다.
- 요청별 훅 구성을 복사하므로 정리 단계에서 등록이 해제되어도 이미 진행 중인 요청은 동일한 훅 구성으로 완료된다.

Metrics는 기본 수집기를 생성하고 시작 시 세 Application 요청 훅을 연결한다. 사용자는 `Metrics('/metrics')`만 등록하면 되며 기존처럼 수집기를 Application의 세 인자에 수동 연결하지 않는다.

Request가 교체되어도 최초 요청을 기준으로 집계를 연결하고, 중첩 호출에서는 외부 요청 맥락을 복원한다. 후속 응답 훅 오류는 완료 수를 중복 증가시키지 않고 실패로 재분류한다. 측정 범위는 Application 처리 완료까지이며 반환 후 전송 시간·스트림 소비 오류는 포함하지 않는다.

## 기본 확장·배너·샘플

Ping, File, FileSystem, Status, Swagger, Specifications, Metrics를 생성자 훅과 `startup/cleanup` 방식으로 이전했다. Specifications와 Metrics는 현재 라우트를 조회하여 뒤에 시작한 확장의 등록도 반영한다.

서버 시작 시 로고·구성 안내를 시작 훅 로그보다 먼저 출력한다. 배너는 확장을 미리 시작하거나 확장 라우트를 조회하지 않고 `str(extension)`과 개수를 출력한다. 표시값에 URI 외 파일 경로·연결 설정이 포함될 수 있으므로 배너 테스트도 인스턴스 표시값을 등록 순서대로 검증하도록 변경했다.

[샘플](../../../samples/Sample.py)은 생성한 확장을 등록하고 FileSystem 변환을 새 요청·응답 훅으로 연결한다. 기존 [명세 저장 스크립트](../../../samples/scripts/DescriptionToFile.py)는 `spec.document()` 호출 전에 Application을 시작하고 `finally`에서 종료하도록 수정했다. 문서 생성만 해도 등록된 전체 확장이 시작되는 현재 동작은 별도 무시작 문서 생성 기능으로 대체하지 않았다.

## 주요 변경 파일

| 범위 | 파일 |
| --- | --- |
| 공개 계약·소유권·수명·등록 API | [Extension](../../../src/Extension.py), [Application](../../../src/Application.py), [공개 export](../../../src/__init__.py) |
| 요청 실행·라우트 연결 | [RunExtension](../../../src/Runners/RunExtension.py), [라우트 도우미](../../../src/Extensions/Utils/Routes.py) |
| 기본 확장·파일 라우트 | [Extensions](../../../src/Extensions), [FileSystem](../../../src/Extensions/FileSystem.py), [Specifications](../../../src/Extensions/Specifications.py), [Metrics](../../../src/Extensions/Metrics.py) |
| 시작 표시 | [Startup](../../../src/Startup.py) |
| 사용 예·명세 저장 | [Sample](../../../samples/Sample.py), [DescriptionToFile](../../../samples/scripts/DescriptionToFile.py) |
| 계약·회귀 테스트 | [Extension 훅](../../../tests/test_extension_hooks.py), [기본 확장](../../../tests/test_builtin_factories.py), [HTTP 확장](../../../tests/test_extensions.py), [배너](../../../tests/test_startup.py), [테스트 모음](../../../tests) |

`test_builtin_factories.py`라는 파일명은 남아 있으나 테스트 대상은 최종 인스턴스 계약이다.

## 검증 기록과 한계

다음은 구현 과정에서 실행한 결과이며 이번 문서 작성 중 새로 실행한 테스트 결과가 아니다.

| 시점·범위 | 결과 |
| --- | --- |
| 인스턴스 구조 재구현 전체 검증, Windows·Python 3.12.10 | 총 198개 중 193개 통과, Gunicorn/POSIX 조건 5개 건너뜀 |
| 훅·기본 확장·export 집중 검증 | 46개 통과 |
| 실제 명세 저장 스크립트 | OpenAPI 3.1.0·24경로, `/api/run/{a}/{b}` 포함, `/metrics`·`/api/doc` 제외 |
| FileSystemRoute 이관 후 관련 회귀 검증 | 48개 통과 |
| 표시 문자열 변경 후 배너·HTTP 확장 회귀 검증 | 26개 통과 |
| 구현 시 확인한 Pylance 범위 | 코어·기본 확장·새 테스트·명세 스크립트 타입 오류 없음, 미사용 힌트 유지 |
| 각 변경 시 형식 검사 | `git diff --check` 통과 |

사용자가 제공한 Linux CI 로그에서는 표시 문자열의 고정 기대값으로 2개가 실패했다. 로컬에서 같은 실패를 재현한 뒤 배너의 `str(extension)` 계약을 검증하도록 수정했다. 이후 관련 26개 테스트는 통과했으나 Linux CI 재실행 통과 여부는 이 기록에서 단정하지 않는다. 건너뛴 사례도 실행 통과에 포함하지 않는다.
