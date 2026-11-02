# 생명 주기 훅 종합 변경 로그

## 개요

[상위 이슈](./ISSUE.md)의 공통 설계와 세 하위 이슈의 구현을 통합해 Application, Extension, RequestRunner에 구성요소별 생명 주기 훅을 도입했다. 기존 요청·응답 필터를 단순히 이름만 바꾸지 않고, 각 구성요소의 책임과 실행 경계에 맞는 공개 계약으로 정리했다.

| 하위 이슈 | 주요 결과 | 상세 변경 로그 |
| --- | --- | --- |
| `feature/4` | Application 생성자 훅, 요청 디스패치 경계와 재진입 제어 | [Application 변경 로그](../4/README.md) |
| `feature/5` | Extension 인스턴스·생성자 훅, 시작·정리 구조, Metrics 관찰 연결 | [Extension 변경 로그](../5/README.md) |
| `feature/6` | RequestRunner 클래스 선언 훅, 기존 필터 제거, 직접 출력 후처리 | [RequestRunner 변경 로그](../6/README.md) |

이 문서는 최종 계약과 하위 작업의 검증 기록을 종합한다. 중간 설계나 이전 하위 작업 시점의 계약이 아니라 세 작업이 반영된 상태를 기준으로 한다.

## 1. 공통 계약과 책임 경계

### 훅 등록

- 훅은 이벤트별 ABC 인터페이스의 `__call__` 계약으로 제공하며 패키지 최상위에서 공개한다.
- 세 구성요소 모두 단일 훅 인스턴스 또는 해당 인터페이스 인스턴스의 시퀀스를 지원한다. 시퀀스는 순서를 보존한 튜플로 보관한다.
- 잘못된 입력과 반환값은 명시적으로 거부한다. 입력 형태가 비슷해도 각 구성요소의 인터페이스는 별도 계약이다.
- 오류 훅은 오류를 관찰하며, 정상 종료 시 원래 예외를 전파한다. 응답 대체·재시도·예외 소비를 수행하는 오류 복구 훅으로 제공하지 않는다.

| 구성요소 | 최종 등록 지점 | 생략·None 처리 |
| --- | --- | --- |
| Application | 생성자 | 생략은 빈 훅, 명시적 None은 TypeError |
| Extension | 생성자, 인스턴스별 계약 | 생략·None은 빈 훅 |
| RequestRunner | `__init_subclass__`, 클래스 선언 계약 | 생략·None은 빈 훅 |

Extension은 초기 상위 설계의 클래스 선언 방식 대신 **생성자에서 인스턴스별 훅을 받는 방식**으로 최종 확정했다. 중간에 검토한 공개 Extension Factory도 최종 API에 포함하지 않는다.

### 구성요소별 실행 경계

| 구성요소 | 훅이 담당하는 경계 | 포함하지 않는 범위 |
| --- | --- | --- |
| Application | 자신의 시작·정리와 준비된 요청의 디스패치·결과 반환 | HTTP 헤더 수신·파싱, 하위 구성요소의 내부 이벤트, 반환 이후 전송·스트림 소비 |
| Extension | 해당 확장의 시작·정리와 자신의 요청 처리 | 전역 요청 관찰의 암묵적 소유, 다른 확장·일반 핸들러 내부 실행, 전송 제어 |
| RequestRunner | 선택된 핸들러의 RunRequest 실행 파이프라인 | Application 라우팅·사전 검사 실패, 반환 이후 서버의 본문 소비·전송 실패 |

Application·Extension에는 별도 생성 완료 훅을 추가하지 않았다. Application 생성자 입력으로 훅을 계약하는 것과 생성 시 훅 이벤트를 실행하는 것은 구분한다.

전체 요청을 관찰해야 하는 확장은 Application 요청 훅을 명시적으로 등록한다. Extension 요청 훅 자체를 전체 요청 관찰 훅으로 확장하지 않는다.

## 2. Application 변경

### 공개 훅 추가

| 생성자 인자 | 인터페이스 | 입력 → 반환 |
| --- | --- | --- |
| `on_startup` | `ApplicationStartup` | 인자 없음 → None |
| `on_cleanup` | `ApplicationCleanup` | 인자 없음 → None |
| `on_request` | `ApplicationRequest` | Request → Request |
| `on_request_response` | `ApplicationRequestResponse` | Request, Optional[Response] → Optional[Response] |
| `on_request_error` | `ApplicationRequestError` | Request, Exception → None |

- Application 인스턴스를 사용자 훅의 인자로 전달하지 않는다.
- 요청 훅이 반환한 Request를 다음 훅과 디스패치에 전달하며, 응답 훅도 등록 순서대로 결과를 연결한다.
- 직접 출력 완료의 응답값은 None이다. 이 경로에서 새 Response를 만들거나 일반 응답을 None으로 버리는 변경은 허용하지 않는다.
- 같은 Application 훅 안에서 같은 Application의 시작·종료·요청 처리를 동기 재호출하면 RuntimeError로 거부한다. 서로 다른 스레드의 독립 요청은 허용한다.
- 훅 객체의 공유 상태에 대한 동기화는 사용자 책임이다.

### 확장 수명 및 동적 요청 훅 관리

- 시작 순서: Application 시작 훅 → 등록 순 Extension 시작 → 실행 상태 전환.
- 종료 순서: 시작 완료 Extension 역순 정리 → Application 정리 훅.
- 정리 중 오류가 발생해도 나머지 정리를 시도하고 첫 오류를 전파한다.
- `add_request_hooks(...)`와 `remove_request_hooks(token)`, 공개 `RequestHookRegistration`을 추가했다.
- 동적 등록은 확장 시작 중, 해제는 소유 확장의 시작·정리 중에만 허용한다. 잘못된 토큰·소유자·중복 등록 및 해제를 거부한다.
- 동적 훅은 등록 순으로 생성자 훅보다 먼저 실행한다. 요청별 훅 구성을 복사해 진행 중인 요청은 같은 구성으로 완료한다.
- 확장 시작 실패나 정리 오류가 있어도 해당 확장 소유 등록을 롤백·해제한다.

## 3. Extension 변경

### 인스턴스 등록과 시작 단계 연결

- `Application(exts=...)`는 생성된 Extension 인스턴스 시퀀스를 튜플로 보관한다. 클래스·Factory·동일 인스턴스 중복 및 서로 다른 Application 간 공유를 거부한다.
- `startup(application)`에서 Application 연결, 라우트 등록 및 자원 준비를 수행하고 사용자 시작 훅을 실행한다.
- `cleanup()`에서 사용자 정리 훅과 확장 자원 회수를 수행한다.
- 추상 호출 계약을 `__call__(request) -> Optional[Response]`로 변경했다. 요청마다 Application을 추가 인자로 전달하지 않는다.
- 기존 별도 `bind/route/routes` 계약 대신 시작 단계에서 연결·등록한다. HTTP 라우트 없는 확장도 허용한다.
- `add_extension_route(extension, route)`는 현재 시작 중인 소유 확장에만 허용하며, 잘못된 Route·핸들러와 동일 method·URL 충돌을 거부한다.
- 시작 실패 시 시작 완료 확장을 역순 정리하고 부분 라우트·동적 훅을 롤백한다. 실패한 확장 자신의 부분 자원 회수는 해당 `startup()` 구현의 책임이다.
- 재시작은 같은 등록 인스턴스를 사용하며, 이전 확장 라우트를 제거한 뒤 재등록한다.

### 공개 훅과 기본 확장 이전

생성자에 `on_startup`, `on_cleanup`, `on_request`, `on_request_response`, `on_request_error`를 추가했다. 인터페이스는 각각 `ExtensionStartup`, `ExtensionCleanup`, `ExtensionRequest`, `ExtensionRequestResponse`, `ExtensionRequestError`이다.

- 시작·정리 훅은 인자 없이 None을 반환한다.
- 요청 훅은 Request를 받아 Request를 반환한다. 기존 필터의 조기 응답 튜플은 사용하지 않는다.
- 응답 훅은 Request와 Optional[Response]를 받아 Optional[Response]를 반환한다. 직접 출력 완료의 None을 새 응답으로 교체할 수 없다.
- 오류 훅은 Request와 Exception을 받아 None을 반환한다.
- Ping, File, FileSystem, Status, Swagger, Specifications, Metrics와 관련 샘플을 새 계약으로 이전했다.
- Metrics는 시작 시 Application 요청 훅을 자동 연결하고 정리 시 해제한다. 요청 교체·중첩 호출의 집계를 연결하고, 후속 응답 훅 실패를 중복 집계 없이 실패로 재분류한다.
- Metrics 측정은 Application 처리 완료까지이며, 반환 이후 전송 시간·스트림 소비 오류는 포함하지 않는다.
- FileSystemRoute를 FileSystem 모듈로 이관했다. 접두 경로 매칭·디코딩 및 일반 라우트 우선·긴 접두사 우선 규칙은 유지했다.

## 4. RequestRunner 변경

| 클래스 선언 인자 | 공개 인터페이스 | 입력 → 반환 |
| --- | --- | --- |
| `on_request` | `RequestRunnerRequest` | Request → Request |
| `on_request_response` | `RequestRunnerRequestResponse` | Request, Response → Response |
| `on_request_error` | `RequestRunnerRequestError` | Request, Exception → None |

- 요청 훅은 CORS 원본 검사, 인증·입력 검증, 본문 처리 및 인스턴스 생성 후 `run()` 직전에 실행한다.
- Request 교체는 다음 훅·핸들러에 전달되지만 라우팅·검증·본문 처리를 다시 수행하지 않는다.
- 부모 훅을 자동 상속·병합하지 않는다. 재사용하려면 하위 클래스 선언에서 명시적으로 전달한다.
- 훅 객체는 요청마다 복제하지 않는다. 여러 요청·Application에서 공유할 수 있으므로 상태 동기화는 사용자 책임이다.
- 오류 경계는 RunRequest 진입 이후 검증·본문 처리·생성·요청 훅·run·직접 출력·종료·응답 후처리의 Exception을 포함한다.
- 오류 훅 실패 시 후속 오류 훅을 중단하고 원래 처리 오류를 예외 체인에 보존한다. 같은 오류 훅에 재귀 통지하지 않는다.

### 응답 후처리와 스트리밍

- 일반·iterable Response는 반환 전에 응답 훅과 CORS를 적용한다.
- stream·chunked·SSE 직접 출력은 writer의 begin에서, WebSocket은 upgrade에서 헤더 전송 전에 후처리한다.
- ResponseWriter는 RequestRunner를 직접 참조하지 않고 주입받은 `on_request_response` 콜백을 실행한다.
- 직접 출력에서도 RequestRunner 응답 훅은 None이 아닌 헤더용 Response를 받는다. 빈 bytes 본문·Content-Length 금지 및 WebSocket 101 상태 유지 제약을 검증한다.
- 응답 후처리는 반환·writer 종료·서버 전송에서 중복 호출하지 않으며, chunk·SSE 이벤트·WebSocket 프레임별 훅은 추가하지 않았다.
- 콜백은 실행 종료 시 해제해 서버가 생성한 오류 응답에 재적용하지 않는다.
- 응답 교체·body 변경 시 폐기 본문을 중복 없이 정리하고, 다른 응답에 인계한 body는 미리 닫지 않는다. 추가 정리 오류가 원래 처리 오류를 덮지 않도록 했다.

## 5. 계층 간 호출 및 완료 의미

| 경로 | 응답 훅 순서 |
| --- | --- |
| 일반 핸들러 반환 | RequestRunner → Application |
| Extension 반환 | Extension → 내부 RequestRunner → Application |
| Extension 직접 출력 | 내부 RequestRunner 전송 전 훅 → Extension 완료 훅 → Application 완료 훅 |

- RequestRunner 응답 훅은 응답 제공 시점의 후처리이며 전체 실행·전송 완료 이벤트가 아니다.
- 직접 출력은 응답 훅 뒤에도 실행·쓰기·flush·종료가 실패할 수 있다. 아직 실행 중인 경계에서 오류 훅이 이어서 호출될 수 있다.
- Extension 안의 writer 콜백 실패는 Extension → RequestRunner → Application 순서로 전파된다.
- 라우팅·Application 사전 검사 실패는 RequestRunner 훅에 전달하지 않는다.
- 반환 이후 서버 전송·스트림 소비 오류로 이미 종료한 Application·RequestRunner 훅을 다시 호출하지 않는다.

## 6. 호환성 변경 및 이전 안내

| 이전 계약 | 최종 계약 |
| --- | --- |
| RequestFilter·ResponseFilter | RequestRunnerRequest·RequestRunnerRequestResponse |
| `onRequest`·`onResponse` | `on_request`·`on_request_response` |
| 요청 필터의 `(Request, Optional[Response])` 조기 응답 | Request 반환만 허용 |
| 오류 훅 이름의 초기 제안 `on_error` | `on_request_error`, 호환 별칭 없음 |
| writer의 `on_response` 콜백 | `on_request_response` |
| Extension 클래스 선언 훅 | 인스턴스 생성자 훅 |
| Extension의 기존 `bind/start/stop/begin/end` 중심 연결·관찰 | `startup(application)`·`cleanup()` 및 명시적 Application 요청 훅 등록 |
| 확장 호출에 Application 전달 | 시작 단계에서 연결하고 요청 시 `extension(request)` |
| `DefChord.FileSystemRoute` 가져오기 | `DefChord.Extensions.FileSystem`에서 가져오기 |
| 명세 생성 시 Application 전달 | Application 시작 후 `spec.document()` 호출 |

공개 Extension Factory는 제공하지 않는다. 내부 RunExtensionFactory는 라우트에 연결할 RequestRunner 어댑터 생성기로 유지한다.

## 7. 시작 출력·샘플·문서

- Python·Uvicorn의 시작 순서를 조정해 로고·구성 안내를 시작 훅 로그보다 먼저 출력한다.
- 배너는 확장을 미리 시작하거나 확장 라우트를 조회하지 않고 `str(extension)`과 개수를 표시한다.
- Application 샘플에 다섯 훅 로그를 연결하고 stdout INFO 로깅을 구성했다.
- 일반 요청 5개와 스트리밍 6개 핸들러에 요청·응답·오류 훅 로그를 연결했다. 오류는 traceback을 포함하고 스트리밍 응답에 X-Request-ID를 추가한다.
- 명세 저장 스크립트를 Application 시작 후 생성·finally 종료 구조로 이전했다.
- 각 하위 명세와 [공통 요구사항](./REQUIREMENTS.md)에 최종 계약 및 계층 간 직접 출력 순서를 반영했다.

## 8. 검증 기록과 한계

아래는 하위 이슈 구현 기록에 남아 있는 실행 결과다. 이 종합 변경 로그 작성 중 새로 실행한 테스트 결과가 아니며, 서로 다른 시점의 테스트 수를 합산하지 않는다.

| 작업·시점 | 기록된 결과 |
| --- | --- |
| Application 구현 전체 검증 | 153개 통과, 5개 건너뜀. py_compile·공백 검사 및 시작 안내/훅 로그 순서 확인 |
| Extension 재구현 전체 검증 | 총 198개 중 193개 통과, 5개 건너뜀 |
| Extension 후속 검증 | FileSystemRoute 이관 관련 48개 통과, 배너·HTTP 확장 관련 26개 통과 |
| 명세 저장 실행 | OpenAPI 3.1.0, 24경로 생성 확인 |
| RequestRunner 핵심 구현 전체 회귀 | 총 218개 중 213개 성공, 5개 건너뜀 |
| 최종 샘플 훅·로그 보강 후 집중 검증 | 관련 33개 성공 |
| 구현 단계 정적·형식 검사 | 하위 기록에 명시된 범위의 Pylance 진단·구문·공백 검사 통과 |

- 5개 건너뜀은 Windows의 Gunicorn/POSIX 환경 제약이며 실행 통과로 간주하지 않는다.
- RequestRunner 전체 회귀는 최종 샘플 로그 보강 이전 결과다. 이후 관련 33개 테스트는 통과했으나 최종 변경 상태의 전체 회귀를 재실행한 기록은 없다.
- Extension 배너 관련 Linux CI 실패는 로컬 재현·수정 및 관련 테스트로 확인했다. 수정 이후 Linux CI 통과 여부는 기록에서 확인되지 않는다.
- 다른 Python 버전 및 배포 산출물 빌드·설치 검증까지 완료했다고 단정하지 않는다.

상세 근거: [Application 구현 기록](../4/IMPLEMENTS.md), [Extension 구현 기록](../5/IMPLEMENTS.md), [RequestRunner 구현 기록](../6/IMPLEMENTS.md).
