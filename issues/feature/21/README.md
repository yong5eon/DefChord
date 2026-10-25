# 오류 응답 처리 개선

## 현재 문제 분석

DefEssential은 예외를 처리하지 않는 상태는 아니다. 요청 처리 과정에서 오류를 관찰하는 훅과, 훅이 처리하지 못한 예외를 HTTP 응답으로 바꾸는 서버 adapter의 기본 동작이 이미 있다. 문제는 애플리케이션·확장·라우트가 오류 상황에 맞는 사용자 정의 `Response`를 반환할 수 없다는 점이다.

### 현재 동작

- `RequestRunner`는 Origin·인증·요청 데이터 검증, handler 생성, 요청 훅, `run()`, 응답 훅과 CORS 처리 중 발생한 `Exception`을 `RequestRunnerRequestError`에 전달한다. 오류 훅의 반환 계약은 `None`이며, 훅을 실행한 뒤 원래 예외를 다시 발생시킨다.
- `Extension`은 확장의 요청 훅, `__call__()` 및 응답 훅에서 발생한 `Exception`을 `ExtensionRequestError`에 전달한다. 이 훅도 `None`을 반환해야 하며, 예외는 다시 발생한다.
- `Application`에는 이미 `on_request_error`와 `ApplicationRequestError`가 있다. 애플리케이션 요청 훅, 라우트 처리, 응답 훅 등 애플리케이션 요청 경계에서 발생한 예외를 관찰한 뒤 다시 발생시킨다. 따라서 Application 오류 훅을 새로 추가하는 것보다 기존 훅의 응답 처리 계약을 확장하는 것이 현재 코드와 맞다.
- 같은 예외가 하위 계층에서 처리되지 않으면 상위 계층에도 전파된다. 예를 들어 Extension 오류는 Extension 훅에서 관찰된 후 RequestRunner 및 Application 오류 훅에서도 관찰될 수 있다. 현재 훅은 이를 중단하거나 응답으로 대체하지 않는다.
- `Adapter.RequestHandler.handle_request()`는 Application 밖으로 전파된 `Error`를 해당 상태 코드와 본문으로 응답한다. 그 밖의 예외는 로그에 기록하고 세부 오류를 노출하지 않는 일반 `500 Internal Server Error` 응답으로 바꾼다. 즉, 기본 HTTP 오류 응답은 존재하지만 이 동작을 애플리케이션이 오류 유형·요청 맥락에 맞게 구성할 수 없다.
- 요청 객체를 만들기 전의 실패는 Application 오류 훅에 도달하지 않는다. 응답 전송이 시작된 뒤의 스트리밍·전송 오류도 이미 전송한 상태 코드와 본문을 교체할 수 없다. 시작·정리 훅의 실패 역시 HTTP 요청 오류와는 별도 생명주기 문제다.

### 해결해야 하는 문제

오류 훅은 현재 로깅·메트릭·추적 같은 관찰 용도로만 사용할 수 있다. 오류 종류나 애플리케이션 정책에 따라 `Response`를 만들고 싶어도 훅에서 반환할 수 없으며, 훅이 `None`을 반환하면 예외가 계속 전파되어 adapter의 기본 오류 응답이 선택된다.

따라서 필요한 변경은 오류 관찰 기능의 신규 도입이 아니라, 기존 오류 처리 훅에 “이 오류를 응답으로 처리했는지”를 표현하는 방법을 추가하는 것이다. 특히 기존 오류 훅이 각 계층에서 이미 호출되고 Application 오류 훅도 구현되어 있다는 점을 고려해야 한다.

## 제안하는 해결 방법

기존 `on_request_error` 훅을 유지하면서 반환 계약을 `None` 또는 `Response`로 확장한다. 새 응답 변환 훅을 별도로 추가하지 않아 기존 설정 구조를 유지하고, 기존처럼 `None`을 반환하는 관찰 훅의 동작도 유지한다.

### 훅 계약과 오류 전파

`RequestRunnerRequestError`, `ExtensionRequestError`, `ApplicationRequestError`의 호출 인자 `(request, error)`는 유지하고 반환 계약을 다음과 같이 정의한다.

| 훅 반환값 | 의미 | 처리 |
| --- | --- | --- |
| `None` | 이 계층에서 오류를 처리하지 않음 | 다음 오류 훅을 실행하고, 해당 계층의 훅이 모두 `None`이면 예외를 상위 계층으로 다시 전파 |
| `Response` | 이 계층에서 오류를 HTTP 응답으로 처리 | 같은 계층의 남은 오류 훅을 중단하고 해당 원래 예외의 전파를 끝낸 뒤 같은 계층 응답 훅은 재실행하지 않고 바깥 계층의 정상 응답 흐름으로 전달 |
| 그 밖의 값 | 훅 계약 위반 | `TypeError` 발생. 오류 훅의 실패를 조용히 무시하지 않음 |

오류 훅에서 예외가 발생하면 그 훅의 예외를 전파하고 원래 처리 중이던 예외를 예외 체인에 보존한다. 성공 응답으로 임의 대체하거나 오류를 숨기지 않는다. 기존 `None` 반환 훅은 계속 관찰자로 동작해야 한다.

### 처리 순서와 우선순위

1. 오류가 발생한 가장 안쪽 처리 계층의 오류 훅부터 등록 순서대로 실행한다.
2. 훅이 `None`을 반환하면 다음 훅을 실행한다. 해당 계층의 모든 훅이 `None`을 반환하면 기존처럼 예외를 바깥 계층으로 전파한다.
3. 처음 `Response`를 반환한 훅을 해당 원래 예외의 처리자로 간주한다. 같은 계층의 남은 오류 훅과 그 원래 예외를 처리하기 위한 더 바깥 계층의 오류 훅은 실행하지 않는다. 단, 응답이 바깥 계층의 정상 처리 중 새로운 예외를 일으키면 해당 바깥 계층의 오류 훅이 실행된다. 이로써 가장 구체적인 계층이 원래 오류 응답을 결정하면서도 바깥 계층의 새 실패를 처리할 수 있다.
4. 각 계층의 정상 응답 생성·검증·응답 훅이 실패하면 해당 계층의 오류 훅이 마지막 대체 경로로 실행된다. 오류 훅이 만든 응답은 오류가 발생한 계층의 응답 훅을 다시 거치지 않고 바깥 계층의 정상 응답 처리만 거친다. 바깥 응답 처리가 실패하면 해당 바깥 계층의 오류 훅이 실행된다.
5. 오류 훅이 모두 `None`을 반환하면 adapter의 기존 기본 동작을 그대로 사용한다. `Error` 하위 타입은 지정된 상태 코드로, 그 밖의 예외는 일반 500 응답으로 변환한다.

예를 들어 RequestRunner 오류 훅이 `Response`를 반환하면 Application의 정상 응답 처리 경로가 이어지지만, RequestRunner 응답 훅은 다시 호출되지 않는다. Extension 오류 훅이 응답을 반환하면 이를 감싼 RequestRunner와 Application의 정상 응답 처리 경로가 이어진다. Application 오류 훅이 응답을 반환하면 더 바깥의 Application 오류 훅은 없으며 adapter가 그 응답을 전송한다.

### 응답 및 스트리밍 제약

- 오류 훅에서 반환하는 값은 `Response` 또는 `None`이어야 한다. 잘못된 값은 명시적인 계약 오류로 처리한다.
- 응답 writer가 이미 시작된 경우 새 `Response`로 상태 코드나 본문을 교체할 수 없다. 이 경우 기존 전송 오류 동작을 유지하고, 오류 응답으로 바꾸려는 시도는 허용하지 않는다.
- 오류 응답의 전송 및 본문 자원 정리는 기존 정상 `Response`와 같은 adapter 책임·자원 소유권 규칙을 따른다.
- 기본 오류 응답의 상태 코드와 본문, 민감한 예외 세부 정보 비노출 동작은 오류 훅이 응답을 반환하지 않는 경우 변경하지 않는다.

### 변경 대상과 검증 범위

- [RequestRunner 오류 훅 계약](../../../src/RequestRunner.py)과 [RequestRunner 실행 경계](../../../src/Runners/RunRequest.py): 반환 타입, 훅 순서, 응답 반환 및 예외 전파.
- [Extension 오류 훅 계약](../../../src/Extension.py)과 [Extension 실행 경계](../../../src/Runners/RunExtension.py): 반환 타입과 응답으로의 전환.
- [Application 오류 훅 계약 및 요청 경계](../../../src/Application.py): 이미 존재하는 훅을 응답 변환에 활용하고, 처리되지 않은 예외는 기존처럼 전파.
- [HTTP adapter 기본 오류 응답](../../../src/Adapter/RequestHandler.py): 미처리 `Error` 및 예기치 않은 예외의 기존 fallback 동작 보존.
- 신규 `docs/ErrorHandling.md`와 `docs/ErrorHandling.en.md`: 새 반환 계약, 계층별 우선순위, 운영상 고려사항 및 스트리밍 제약을 상세히 설명.
- 구현 시 `docs/LifecycleAndErrors.md`와 `docs/LifecycleAndErrors.en.md`를 각각 `docs/Lifecycle.md`와 `docs/Lifecycle.en.md`로 변경하고, 생명주기 흐름만 설명하도록 정리.
- [한국어 매뉴얼 목차](../../../docs/README.md)와 영어판: 오류 처리를 독립 주제로 추가.

검증에서는 각 계층별로 `Response` 반환, `None` 반환 후 상위 계층 전파, 오류 훅 순서와 조기 종료, 오류 훅 자체의 예외·잘못된 반환값, 이미 시작된 직접 출력, 기존 `Error` 및 일반 예외의 adapter 응답을 확인한다. 기존의 `None` 반환 관찰 훅과 오류가 없는 정상 요청의 동작도 유지되는지 확인한다.

## 범위에서 제외할 동작

- 요청 생성 전 실패, 응답 전송 이후의 네트워크·스트리밍 실패를 새 HTTP 응답으로 변환하지 않는다.
- Application 시작·정리 실패의 생명주기 계약은 변경하지 않는다.
- 오류 훅이 모두 처리하지 않은 경우의 상태 코드·기본 메시지 정책은 이번 제안에서 바꾸지 않는다.

## 근거가 되는 현재 코드와 문서

- `RequestRunner`·Extension·Application의 현재 오류 훅은 모두 `None` 반환 계약이며 오류를 관찰한 뒤 다시 전파한다.
- Application 요청 오류 훅은 생성자 및 확장 훅 등록 API에 이미 포함되어 있다.
- 서버 adapter는 미처리 오류를 HTTP 응답으로 변환한다.
- 현재 매뉴얼은 오류 훅이 관찰 전용이고 예외가 계속 전파된다고 설명한다.

세부 동작의 근거는 [오류 훅 계약](../../../src/RequestRunner.py), [Extension 계약](../../../src/Extension.py), [Application 계약](../../../src/Application.py), [adapter의 오류 응답 처리](../../../src/Adapter/RequestHandler.py)와 현재 [생명주기·오류 매뉴얼](../../../docs/LifecycleAndErrors.md)에서 확인할 수 있다. 별도 생명주기·오류 처리 매뉴얼의 분리와 파일명 변경은 구현 계획에 포함한다.

## 이슈 문서

- 요구사항: [REQUIREMENTS.md](./REQUIREMENTS.md)
- 작업 계획: [PLAN.md](./PLAN.md)
