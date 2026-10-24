# RequestRunner 생명 주기 훅 요구사항 명세서

## 1. 목적과 상태

[RequestRunner 이슈](./ISSUE.md)의 기존 요청·응답 필터를 생명 주기 훅으로 대체한다. 선택된 핸들러의 요청 실행 경계, 공개 계약, 계층 간 호출 관계, 호환성 변경과 수용 기준을 정의한다.

이 문서는 구현의 기준이 되는 요구사항 명세다. Python 구현·샘플·기존 사용처에 아래 계약을 반영했으며, 실행한 검증과 환경 제약은 [작업 계획서의 검증 기록](./PLAN.md#7-완료-체크리스트와-검증-기록)에 기록한다.

### 1.1 근거

- [상위 이슈](../2/ISSUE.md), [상위 공통 명세](../2/REQUIREMENTS.md)
- [Application 이슈](../4/ISSUE.md), [Application 명세](../4/REQUIREMENTS.md)
- [Extension 이슈](../5/ISSUE.md), [Extension 최신 명세](../5/REQUIREMENTS.md)
- [RequestRunner 선언 계약](../../../src/RequestRunner.py), [요청 실행기](../../../src/Runners/RunRequest.py)
- [Application](../../../src/Application.py), [Extension 실행기](../../../src/Runners/RunExtension.py)
- [응답 writer](../../../src/IO/ResponseWriter.py), [공통 서버 요청 처리기](../../../src/Adapter/RequestHandler.py)
- [CORS 처리](../../../src/CrossOriginResourceSharing.py), [공개 패키지 내보내기](../../../src/__init__.py)

### 1.2 이슈 분석과 사용자 확인 사항

| 근거 | 분석 및 적용 |
| --- | --- |
| 상위 feature/2 | RequestRunner 훅은 `__init_subclass__`에서 설정하고 단일·복수 훅을 지원한다. 구성요소 경계, 실패, 상속, 호환성은 이 하위 명세에서 구체화한다. |
| 연관 feature/4 | Application은 디스패치 바깥 경계다. 요청 훅은 RequestRunner보다 먼저, 정상 응답·전파된 오류 훅은 RequestRunner 경계 종료 뒤 실행한다. |
| 연관 feature/5 | 최신 계약은 Extension 인스턴스 등록과 생성자 훅이다. Extension 요청 훅은 해당 확장 실행에만 적용하며 일반 핸들러·전체 요청 관찰과 구분한다. |
| 대상 feature/6 | 기존 RequestFilter 방식 제거와 요청·응답·오류 훅 도입이 핵심이다. ResponseFilter의 처리도 새 응답 훅으로 대체한다. |

분석 후 다음 동작을 사용자에게 확인했다.

1. 이슈 본문의 `on_error` 대신 연관 이슈와 같은 `on_request_error`를 사용한다.
2. 요청 훅은 Request만 반환한다. 기존 `(Request, Optional[Response])` 조기 응답 계약은 제거한다.
3. 후속 논의에 따라 요청 훅은 검증·본문 처리·인스턴스 생성 후 `run()` 호출 직전에 실행한다. 검증·본문 처리·인스턴스 생성 실패는 계속 오류 관찰 경계에 포함한다.
4. 응답 훅은 Response 반환 경로에서는 RunRequest가 호출하고, 직접 출력에서는 ResponseWriter에 주입한 콜백으로 `begin()` 또는 `upgrade()`의 헤더 전송 전에 호출한다. 두 경로 모두 실제 Response를 받고 Response를 반환한다.
5. 데이터별 읽기·쓰기, SSE 이벤트 및 WebSocket 메시지 제어는 reader·writer의 별도 확장 관심사이며 이번 생명 주기 훅에 추가하지 않는다.

이 명세에서 상위 문서의 변경 전 조사 기록이나 Application 명세의 과거 Extension `begin/end` 설명을 최신 Extension 계약으로 사용하지 않는다.

## 2. 현재 동작과 변경 이유

아래는 변경 전 구현 분석이다.

- RequestRunner 클래스의 `onRequest`, `onResponse`는 각각 RequestFilter·ResponseFilter 인스턴스 또는 시퀀스를 받는다. 설정은 RequestProperties에 보관한다.
- 요청 실행 순서는 CORS 원본 검사 → 인증 → 파라미터 → 쿼리 → 헤더 검증 → 본문 처리 → 핸들러 인스턴스 생성 → 요청 필터 → `run()` → 응답 필터다.
- 요청 필터는 `(request, response)`를 반환한다. Response가 있으면 `run()`과 응답 필터를 생략하고 CORS를 적용해 반환한다.
- 반환 응답은 응답 필터와 CORS를 거친다. 직접 출력은 writer의 응답 콜백을 통해 헤더 전송 전에 같은 후처리를 수행한다.
- `run()`이 직접 출력을 시작했다면 Response를 동시에 반환할 수 없으며 실행기가 writer 종료를 완료한다.
- 통합된 RequestRunner 오류 훅은 없다. 인스턴스 생성 전 오류도 호출자에게 전파된다.
- Application은 RunRequest 호출 전에 라우팅, Content-Type 및 본문 처리기 설정에 대한 사전 검사를 수행한다. 이 사전 검사와 RunRequest 내부 검증은 서로 다른 경계다.

새 계약은 기존 요청·응답 필터의 연결 위치를 활용하면서 요청 진입·응답 제공·오류 관찰 계약을 정리한다. 조기 응답 튜플은 제거하지만 전송 전 헤더 변환은 보존한다. 훅이 없을 때의 일반 처리와 전송 안전성은 보존하되, 기존 필터 사용 API 변경은 명시적인 비호환 변경으로 취급한다.

## 3. 책임과 실행 경계

### RR-01. 선언과 요청 실행 분리

- 훅 설정은 RequestRunner의 `__init_subclass__`에서 클래스별로 구성한다.
- 클래스 선언이나 Application 등록만으로 훅을 실행하지 않는다.
- Application에는 기존처럼 핸들러 클래스를 등록하고, 정상 요청마다 새 핸들러 인스턴스를 생성한다. 검증 실패 시 인스턴스를 만들지 않는다.
- 훅은 핸들러 인스턴스의 메서드가 아니라 클래스 설정에 보관한 별도 인터페이스 인스턴스다.

### RR-02. 포함 범위

경계는 선택된 핸들러의 `RunRequest.run(request)` 진입부터 결과 반환 또는 예외 전파까지다.

포함하는 단계는 요청 훅, CORS 원본 검사, 인증·파라미터·쿼리·헤더 검증, 본문 처리, 핸들러 생성, `run()`, 실행 중 직접 출력과 종료, 정상 응답 훅, 반환 응답의 CORS 후처리다.

각 단계의 Exception은 해당 RequestRunner 오류 훅의 대상이다. `KeyboardInterrupt`, `SystemExit` 같은 BaseException 전체를 사용자 오류 관찰 대상으로 확장하지 않는다.

### RR-03. 제외 범위

- Application 구성·시작·종료와 라우트 선택
- RunRequest 진입 전 Application의 사전 검사 실패
- HTTP 요청 수신·파싱과 연결 관리
- 다른 핸들러나 다른 Extension의 독립 실행
- 반환 이후 서버의 응답 전송, iterable 본문 소비 및 연결 종료
- 별도의 RequestRunner 시작·정리 훅, 비동기 훅, 자동 스케줄링 기능

`Application(request)`와 서버 요청 경로 모두 같은 RequestRunner 실행 계약을 사용한다. `runner.run(request)` 직접 호출은 사용자 구현 메서드 호출이므로 프레임워크 파이프라인과 훅 실행을 자동 보장하지 않는다.

## 4. 공개 훅 계약

### RR-04. 이름과 시그니처

각 인터페이스는 ABC 기반의 `__call__` 계약을 제공하며 패키지 최상위에서도 가져올 수 있어야 한다.

| 인터페이스 | 클래스 선언 인자 | `__call__` 입력 | 반환 |
| --- | --- | --- | --- |
| `RequestRunnerRequest` | `on_request` | `request: Request` | `Request` |
| `RequestRunnerRequestResponse` | `on_request_response` | `request: Request, response: Response` | `Response` |
| `RequestRunnerRequestError` | `on_request_error` | `request: Request, error: Exception` | `None` |

Application·Extension·핸들러 인스턴스 또는 별도 범용 Context를 훅 인자로 추가하지 않는다. `on_error`는 별칭으로 제공하지 않는다.

RequestRunner 응답 훅은 전체 실행 완료가 아니라 응답을 제공하는 시점의 후처리다. 직접 출력에서 `None`을 전달하지 않으며, 실행 완료 후 호출되는 Application·Extension 응답 훅의 `Optional[Response]` 계약과 구분한다.

### RR-05. 단일·복수 입력과 검증

- 각 인자는 해당 인터페이스 인스턴스 하나, 해당 인스턴스의 Sequence 또는 `None`을 받는다.
- 생략하거나 `None`이면 해당 이벤트의 훅이 없다. 이는 기존 RequestRunner의 선택적 설정 및 Extension 생성자 관례를 따른다.
- 단일 입력은 한 개짜리 튜플로, 시퀀스는 입력 순서를 보존한 튜플로 복사한다.
- 문자열·바이트열, 일반 함수, 인터페이스 클래스 자체, 잘못된 원소 및 지원하지 않는 iterable은 클래스 선언 시 TypeError로 거부한다.
- 호출 결과도 실행 시 검증한다. 잘못된 요청·응답·오류 훅 반환값은 TypeError이며 조용히 무시하지 않는다.
- 복수 훅은 입력 순서대로 실행한다. 중간 실패 시 같은 이벤트의 나머지 훅을 실행하지 않는다.

### RR-06. 상속과 상태 공유

- 현행 클래스 설정 구성 방식처럼 하위 클래스 선언 시 전달한 훅만 해당 클래스의 설정으로 삼는다.
- 부모 훅을 자동 병합하거나 암묵적으로 상속하지 않는다. 인자를 생략한 하위 클래스는 빈 훅 목록을 갖는다.
- 부모 훅 재사용은 사용자가 해당 인스턴스나 시퀀스를 명시적으로 전달한다.
- 훅 객체는 요청마다 새로 만들거나 복제하지 않는다. 같은 클래스의 동시 요청과 같은 클래스를 등록한 여러 Application에서 공유될 수 있다.
- 동일 객체를 서로 다른 클래스에 명시적으로 전달한 경우에도 공유된다. 프레임워크는 사용자 상태를 자동 잠금·동기화하지 않으며 별도 프로세스 간 상태 공유도 보장하지 않는다.
- 다른 클래스의 선언이나 입력 리스트 수정이 이미 구성된 클래스의 훅 목록을 바꾸지 않아야 한다.

## 5. 요청 및 정상 응답 처리

### RR-07. 요청 훅과 검증 순서

정상 경로의 순서는 다음과 같다.

1. CORS 원본 검사를 수행한다.
2. 인증 → 파라미터 → 쿼리 → 헤더 검증을 기존 순서대로 수행한다.
3. 본문 처리기가 있으면 본문을 처리해 Request에 설정한다.
4. 선택된 핸들러 인스턴스를 생성한다.
5. 요청 훅을 순서대로 실행하고 각 반환 Request를 다음 훅에 전달한다.
6. 최종 Request의 ResponseWriter가 있으면 요청별 응답 후처리 콜백을 연결하고 `run(request)`을 호출한다.
7. 직접 출력은 `begin()` 또는 `upgrade()`에서 응답 훅 → CORS → 출력별 검증 → 헤더 전송을 수행한다. 이후 `run()`이 반환하면 상태를 검증하고 writer 종료를 완료하며 `None`을 반환한다.
8. Response 반환은 RunRequest에서 응답 훅 → CORS를 수행하고 최종 응답을 호출자에게 반환한다.

요청 훅의 반환값은 다음 요청 훅·`run()`·응답 및 오류 훅에 사용한다. 이미 끝난 검증·본문 처리를 다시 실행하지 않는다. 요청 훅이 실패하거나 잘못된 값을 반환하면 마지막으로 유효했던 Request를 오류 훅에 전달한다.

요청 교체는 이미 선택된 핸들러를 다시 라우팅하지 않는다. 교체 Request에 필요한 검증된 상태·본문·라우트 파라미터·reader·writer를 보존하는 책임은 사용자 훅에 있다. 프레임워크가 다른 요청의 전송 상태를 임의로 생성하거나 폴백하지 않는다.

스트리밍 입력에서는 본문 처리기가 스트림을 준비하고 실제 읽기는 `run()`에서 수행할 수 있다. 요청 훅 시점을 전체 업로드 완료로 표현하지 않는다.

요청 훅은 검증을 우회하는 조기 응답 경로가 아니다. Response나 기존 튜플을 반환하면 TypeError로 실패하며 `run()`을 생략하는 성공 경로를 제공하지 않는다.

### RR-08. 일반 응답

- `run()`이 Response를 반환하고 직접 출력이 시작되지 않았으면 정상 응답 훅에 해당 응답을 전달한다.
- 응답 훅은 같은 Response를 수정해 반환하거나 다른 Response로 교체할 수 있다. 반환값을 다음 훅과 최종 CORS 처리에 전달한다.
- 응답 훅이 `None`을 반환하는 동작은 TypeError다.
- 일반 응답의 훅 완료는 전송 완료를 뜻하지 않는다. iterable 본문을 미리 소비하지 않는다.
- 후속 응답 훅이나 CORS가 실패하면 정상 반환하지 않고 오류 훅을 실행한다. 이미 실행한 정상 응답 훅을 되돌리거나 다시 호출하지 않는다.

### RR-09. 직접 출력과 프로토콜 전환

- `run()`이 writer로 출력했다면 `None`을 반환해야 한다. writer 시작 없이 `None`을 반환하는 동작은 TypeError다.
- 이미 직접 출력을 시작하고 Response도 반환하면 해당 반환 응답을 정리한 뒤 RuntimeError로 실패한다.
- RunRequest는 요청별 Request를 캡처한 응답 후처리 콜백을 ResponseWriter에 주입한다. writer는 RequestRunner나 사용자 인터페이스를 직접 알지 않고 `Response -> Response` 콜백만 호출한다.
- StreamWriter·ChunkedStreamWriter·SSE의 `begin()`과 WebSocket의 `upgrade()`에서 헤더 전송 전에 같은 후처리를 수행한다.
- 응답 훅은 헤더용 Response를 수정하거나 교체해 반환할 수 있다. 직접 출력용 본문은 빈 bytes여야 하며 Content-Length를 설정할 수 없다. WebSocket 전환은 101 상태를 유지해야 한다.
- CORS는 응답 훅 이후, 전송 전에 적용한다. 중복 헤더 전송 방지 및 출력별 제약을 약화하지 않는다.
- 직접 출력 후 `run()`이 반환하거나 writer가 종료될 때 응답 훅을 다시 호출하지 않는다. chunk·SSE 이벤트·WebSocket 프레임마다 호출하지 않는다.
- Response 반환 경로에서는 RunRequest가 같은 후처리를 직접 수행한다. 이후 서버 전송에서는 기존 처리 완료 표시를 이용해 콜백을 재실행하지 않는다.
- 콜백은 해당 실행 경계에서만 유효하다. 오류 응답이나 반환 이후의 출력에 폐기된 RequestRunner 콜백이 적용되지 않도록 정상·실패 종료 모두 연결을 해제한다.
- 응답 훅 호출 뒤에도 `run()`의 쓰기·flush·종료 등이 실패하면 오류 훅을 실행할 수 있다. 응답 훅 호출을 전체 처리 성공으로 취급하지 않는다.
- `run()` 안에서 발생한 출력·flush·종료·프로토콜 처리 오류는 아직 RequestRunner 경계 안이므로 오류 훅의 대상이다.
- 반환 이후 서버가 수행하는 전송·본문 소비 실패에는 종료된 RequestRunner 훅을 다시 호출하지 않는다.

### RR-10. 응답 자원

- 응답 교체로 더 이상 사용하지 않는 본문은 닫고, 최종 응답의 본문은 호출자에게 소유권을 넘긴다.
- 동일 Response의 body를 교체한 경우 이전 body를 닫는다. 다른 Response가 동일 body를 이어받는 경우에는 그 body를 미리 닫지 않는다.
- 응답 훅 실패, 잘못된 반환값, CORS 후처리 실패 및 직접 출력과 반환 응답의 충돌에서도 실행기가 보유한 폐기 응답을 정리한다.
- 정상 반환한 최종 응답의 정리는 기존 서버 요청 처리기 또는 직접 호출자의 책임이다.
- 정리 오류를 숨기지 않는다. 처리 오류와 정리 오류가 겹치면 원래 처리 오류의 전파를 유지하고 추가 정리 오류를 기존 로깅 방식으로 기록한다. 단독 정리 실패는 경계 안의 오류로 전파한다.

## 6. 오류와 계층 간 관계

### RR-11. 오류 훅

- 경계 안에서 Exception이 발생하면 오류 훅에 마지막 유효 Request와 해당 예외를 전달한다.
- 요청 훅·검증·본문 처리·생성·`run()`·직접 출력 종료·응답 훅·CORS 오류를 모두 포함한다.
- 오류 훅은 관찰 전용이다. 응답 생성·예외 소비·자동 재시도·성공 복구를 제공하지 않는다.
- 모든 오류 훅이 정상 완료하면 원래 예외를 호출자에게 전파한다.
- 오류 훅 자체가 실패하거나 `None` 이외의 값을 반환하면 후속 오류 훅을 중단하고 해당 오류를 전파한다. 원래 처리 오류는 예외 체인에 보존한다.
- 오류 훅 실패를 같은 RequestRunner 오류 훅에 재귀 통지하지 않는다.
- 오류 발생 이후에는 아직 실행하지 않은 정상 응답 훅을 호출하지 않는다.
- 오류의 HTTP 응답 변환은 기존 공통 서버 요청 처리기의 책임이다. 전송이 시작된 뒤에는 새 오류 응답을 보내지 않는다.

### RR-12. Application과 Extension 순서

일반 Response 반환의 정상 순서는 Application 요청 훅 → 검증·본문 처리·생성 → RequestRunner 요청 훅 → `run()` → RequestRunner 응답 훅 → Application 응답 훅이다.

확장 라우트는 내부 RequestRunner의 `run()`이 Extension 실행기에 위임하므로 정상 순서는 다음과 같다.

1. Application 요청 훅
2. 내부 RequestRunner 검증·본문 처리·생성 후 요청 훅
3. 해당 Extension 요청 훅 → `extension(request)` → Extension 응답 훅
4. 내부 RequestRunner 실행 완료 및 응답 훅
5. Application 응답 훅

이는 경계가 중첩되는 관계이지 Extension 훅을 RequestRunner 훅으로 복사해 등록하는 관계가 아니다. 내부 RequestRunner에 훅이 없으면 호출도 없다.

직접 출력은 예외적으로 `run()` 실행 중 writer의 `begin()` 또는 `upgrade()`에서 RequestRunner 응답 훅이 먼저 실행된다. Extension이 직접 출력하면 RequestRunner 응답 훅 → 출력·Extension 처리 완료 → Extension 응답 훅 → Application 응답 훅 순서다. 이는 Extension 내부 이벤트 구독이 아니라 외부 실행기가 소유한 응답 후처리다. 연관 명세의 응답 훅 순서 설명은 일반 Response 반환 기준으로 해석하며, 구현 시 직접 출력의 이 순서 차이를 관련 문서에도 반영한다.

| 실패 위치 | 오류 관찰 순서 |
| --- | --- |
| 라우팅·Application 사전 검사 | Application만 실행 |
| RequestRunner 요청 훅·검증·본문 처리·생성 | 해당 RequestRunner → Application |
| Extension 요청 훅·처리·응답 훅 | 해당 Extension → 내부 RequestRunner → Application |
| Extension 정상 반환 뒤 RequestRunner 후처리 | 해당 RequestRunner → Application. 종료한 Extension 오류 훅은 호출하지 않음 |
| RequestRunner 정상 반환 뒤 Application 응답 훅 | Application만 실행 |
| Application 반환 뒤 서버 전송·본문 소비 | 종료한 세 구성요소의 요청 오류 훅을 다시 호출하지 않음 |

Application 및 Extension의 이벤트별 복수 훅 순서와 오류 체인 정책은 각 최신 명세를 유지한다. Metrics의 전체 요청 관찰을 RequestRunner 훅으로 옮기거나 모든 Extension 요청 훅을 모든 요청에 호출하지 않는다.

## 7. 호환성 및 변경 대상

### RR-13. 의도적인 비호환 변경

| 기존 계약 | 변경 후 |
| --- | --- |
| `RequestFilter`, `ResponseFilter` | 제거하고 세 RequestRunner 훅 인터페이스로 대체 |
| 클래스 인자 `onRequest`, `onResponse` | 제거하고 `on_request`, `on_request_response`, `on_request_error` 사용 |
| RequestProperties의 필터 저장 | 이벤트별 훅 튜플 저장으로 변경. `on_response`는 `on_request_response`로 대체 |
| 요청 필터의 조기 응답 튜플 | 제거. 요청 훅은 Request만 반환 |
| 검증·본문 처리·생성 후 요청 필터 | 같은 위치에서 `run()` 직전 요청 훅 |
| 직접 출력 전 사용자 응답 필터 | 같은 전송 전 위치에서 주입된 응답 훅 실행 |

기존 이름이나 `on_error`의 호환 별칭·자동 변환은 추가하지 않는다. 제거한 클래스 인자 사용은 명시적으로 실패해야 하며, 폐기한 필터를 새 계약으로 잘못 받아들이지 않는다.

필터를 설정하지 않은 기존 핸들러의 라우팅·검증 순서·본문 처리·인스턴스 수명·일반 응답·CORS·직접 출력·전송 안전성은 유지한다. 일반 응답과 직접 출력 헤더의 변환 용도는 새 응답 훅으로 이전한다. 조기 응답 튜플은 동등한 대체 기능이 없음을 문서화한다.

### RR-14. 구현 시 반영할 표면

- [RequestRunner](../../../src/RequestRunner.py), [RunRequest](../../../src/Runners/RunRequest.py), [공개 내보내기](../../../src/__init__.py)의 인터페이스·설정·실행 경로
- [ResponseWriter](../../../src/IO/ResponseWriter.py) 콜백 주입·해제·중복 호출 방지와 [CORS](../../../src/CrossOriginResourceSharing.py)의 전송 전 처리
- [Extension 실행기](../../../src/Runners/RunExtension.py) 및 기본 확장과의 중첩 경계 회귀
- [샘플](../../../samples/Sample.py)의 기존 필터 사용과 새 훅 예제
- [핵심 테스트](../../../tests/test_core.py), [기능 테스트](../../../tests/test_features.py), [writer 테스트](../../../tests/test_writers.py), [WebSocket 테스트](../../../tests/test_websocket.py)의 기존 필터 기대값 이전
- [Application 훅 테스트](../../../tests/test_application_hooks.py), [Extension 훅 테스트](../../../tests/test_extension_hooks.py), [공개 API 테스트](../../../tests/test_exports.py), [전송 적합성 테스트](../../../tests/test_transport_conformance.py) 등 관련 회귀

과거 동작을 설명하는 상위·연관 명세의 조사 기록을 무조건 삭제하지 않는다. 구현 완료 시 최신 계약의 참조와 검증 결과를 필요한 문서에 반영한다.

## 8. 수용 기준과 검증

| ID | 검증할 결과 |
| --- | --- |
| AC-01 | 세 훅 인터페이스와 클래스 선언 인자가 정의되고 모듈·최상위 패키지에서 공개된다. |
| AC-02 | 단일·복수·빈 시퀀스·생략·None을 처리하고, 잘못된 타입·원소·문자열·클래스·지원하지 않는 iterable을 선언 시 거부한다. |
| AC-03 | 입력 시퀀스 복사, 하위 클래스 미설정·명시적 재사용·대체가 명세와 같고 다른 클래스 설정을 변경하지 않는다. |
| AC-04 | CORS 원본 → 인증 → 파라미터 → 쿼리 → 헤더 → 본문 → 생성 → 요청 훅 → run 순서와 응답 경로별 응답 훅 → CORS → 반환 또는 헤더 전송을 검증한다. |
| AC-05 | Request 교체값이 다음 훅·run·주입 콜백에 전달되고 검증·본문 처리는 반복하지 않으며, 잘못된 반환 및 기존 조기 응답 튜플은 오류가 된다. |
| AC-06 | 일반 응답의 수정·교체·복수 훅 전달을 검증하고 직접 출력 없는 None 반환을 거부한다. |
| AC-07 | 직접 출력·SSE는 begin, WebSocket은 upgrade에서 Response로 헤더 전송 전 한 번 호출된다. 반환·종료·서버 전송 시 중복이 없고 실패 후 서버 오류 응답에 콜백이 재적용되지 않는다. |
| AC-08 | 직접 출력의 CORS·101·본문·Content-Length 제약, 중복 전송 방지, writer 종료와 오류 전파가 유지된다. |
| AC-09 | 경계 안 각 실패 지점에서 오류 훅 호출 횟수·예외 동일성·마지막 유효 Request·후속 정상 훅 비호출을 검증한다. |
| AC-10 | 복수 훅의 입력 순서·중간 중단, 오류 훅 실패 시 비재귀·후속 중단·원래 오류 체인을 검증한다. |
| AC-11 | 응답 교체·동일 body 공유·body 변경·훅 실패·CORS 실패·반환 충돌의 본문 close 횟수와 정리 오류 정책을 검증한다. |
| AC-12 | 라우팅·Application 사전 검사 실패에는 RequestRunner 훅이 없고, 내부 검증 실패에는 RequestRunner 오류 훅만 먼저 실행된다. |
| AC-13 | 일반·Extension 라우트의 반환 응답과 직접 출력을 각각 검증한다. 직접 출력은 Extension 응답 훅보다 RequestRunner 응답 훅이 먼저 실행되며 다른 핸들러·확장의 훅은 호출되지 않는다. |
| AC-14 | 반환 후 스트림 소비·전송 실패에는 종료된 훅이 재호출되지 않으며, run 내부 직접 출력 실패는 해당 오류 훅으로 관찰된다. |
| AC-15 | 새 훅 미설정 핸들러의 동작, 동시 요청별 Request·Response 격리, 클래스·Application 간 훅 객체 공유 특성을 검증한다. |
| AC-16 | 폐기 API가 공개 계약에서 제거되고 기존 인자 사용은 실패한다. 샘플·API 문서·관련 테스트가 새 계약으로 이전된다. |

검증은 새 RequestRunner 훅 집중 테스트와 영향받는 기존 테스트부터 실행한다. 훅 순서·횟수, 예외 체인, 자원 정리 횟수처럼 요구사항 자체를 관찰하며, 단순 HTTP 성공 코드만으로 완료 판정하지 않는다.

구현 완료 기준은 위 수용 기준과 관련 회귀 검증 통과 및 비호환 변경 문서화다. 집중 테스트와 전체 회귀 결과를 작업 계획서에 기록했으며, 현재 환경에서 실행하지 못한 Gunicorn 검증은 별도로 구분한다.
