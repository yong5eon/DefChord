# RequestRunner 생명 주기 훅 구현 기록

## 1. 개요

[요구사항 명세서](./REQUIREMENTS.md)와 [작업 계획서](./PLAN.md)에 따라 기존 요청·응답 필터를 세 생명 주기 훅으로 대체했다. 이후 일반 요청 및 스트리밍 샘플에 세 훅의 로그를 연결하고 정상·실패 경로를 검증했다.

이 문서는 최종 공개 계약, 실행 구조, 호환성 변경과 실제 검증 결과를 기록한다. reader·writer의 데이터별 제어 훅은 이번 범위에 포함하지 않는다.

## 2. 공개 계약

각 훅은 ABC의 `__call__` 계약으로 제공하며, 모듈 및 패키지 최상위에서 가져올 수 있다.

| 인터페이스 | 클래스 선언 인자 | 입력 | 반환 |
| --- | --- | --- | --- |
| `RequestRunnerRequest` | `on_request` | `Request` | `Request` |
| `RequestRunnerRequestResponse` | `on_request_response` | `Request`, `Response` | `Response` |
| `RequestRunnerRequestError` | `on_request_error` | `Request`, `Exception` | `None` |

- 클래스 선언의 `__init_subclass__`에서 단일 인터페이스 인스턴스, 해당 인스턴스의 시퀀스 또는 `None`을 받는다.
- 생략·None은 빈 튜플, 단일 입력은 한 개짜리 튜플, 시퀀스는 입력 순서를 보존한 튜플로 구성한다.
- 문자열·잘못된 원소·일반 함수·인터페이스 클래스 자체·지원하지 않는 iterable은 선언 시 TypeError로 거부한다.
- 부모 훅을 자동 상속·병합하지 않는다. 하위 클래스에서 재사용하려면 명시적으로 전달한다.
- 훅 객체는 요청마다 복제하지 않는다. 같은 클래스를 사용하는 동시 요청·여러 Application에서 공유될 수 있으며 상태 동기화는 사용자 책임이다.

## 3. 실행 구조

### 3.1 요청 진입

[RunRequest](../../../src/Runners/RunRequest.py)는 다음 순서로 실행한다.

1. CORS 원본 검사
2. 인증 → 파라미터 → 쿼리 → 헤더 검증
3. 본문 처리와 Request의 body 설정
4. 핸들러 인스턴스 생성
5. 요청 훅 순차 실행
6. 최종 Request의 writer에 응답 후처리 콜백 연결
7. `run(request)` 호출

요청 훅은 `run()` 직전에 실행한다. 각 반환 Request를 다음 훅·핸들러·응답 및 오류 훅에서 사용하며, 교체로 라우팅·검증·본문 처리를 다시 수행하지 않는다. 훅 실패나 잘못된 반환값 발생 시 마지막 유효 Request로 오류를 관찰한다.

스트리밍 입력의 본문 처리는 reader 준비만 수행할 수 있다. 요청 훅 실행이 전체 업로드 완료를 뜻하지 않으며 실제 읽기는 핸들러 안에서 이어질 수 있다.

### 3.2 응답 반환과 직접 출력

응답 훅과 CORS는 요청별 공통 후처리 함수로 구성한다.

| 응답 방식 | 후처리 호출 위치 |
| --- | --- |
| 일반·iterable Response 반환 | RunRequest에서 반환 응답에 직접 적용 |
| StreamWriter·ChunkedStreamWriter | ResponseWriter의 `begin()`에서 헤더 전송 전 적용 |
| SSE | 내부 StreamWriter의 begin 경로에서 첫 이벤트 전 적용 |
| WebSocket | ResponseWriter의 `upgrade()`에서 101 헤더 전송 전 적용 |

[ResponseWriter](../../../src/IO/ResponseWriter.py)는 RequestRunner를 직접 참조하지 않고 `on_request_response`에 주입된 `Response -> Response` 콜백만 호출한다. 콜백은 Request를 캡처해 사용자 응답 훅을 실행하고 최종 응답에 CORS를 적용한다.

- 직접 출력에서도 훅은 None이 아니라 헤더용 Response를 받고 Response를 반환한다.
- 직접 출력용 본문은 빈 bytes여야 하며 Content-Length를 설정할 수 없다. WebSocket의 101 상태도 유지해야 한다.
- 직접 출력 이후 `run()` 반환·writer 종료에서 훅을 반복하지 않는다. chunk·SSE 이벤트·WebSocket 프레임마다 호출하지 않는다.
- 반환 응답은 기존 서버의 `filtered=True` 경로로 전송하여 후처리를 반복하지 않는다.
- RunRequest 종료 시 finally에서 연결을 해제한다. 실패 후 서버가 생성하는 오류 응답에 이전 콜백을 재적용하지 않는다.
- 직접 출력과 Response 반환을 동시에 수행하거나 출력 시작 없이 None을 반환하면 오류다.

응답 훅은 응답 제공 시점의 후처리이며 전체 실행·전송 완료 이벤트가 아니다. 직접 출력은 응답 훅 뒤에도 쓰기·flush·종료 오류가 발생할 수 있다.

### 3.3 오류 경계와 자원 정리

- RunRequest 진입 이후 검증·본문 처리·생성·요청 훅·run·직접 출력·종료·응답 후처리의 Exception을 오류 훅에 전달한다.
- 오류 훅은 관찰 전용이며 응답 변환·재시도·예외 소비를 하지 않는다. 정상 완료하면 원래 예외를 전파한다.
- 오류 훅 자체가 실패하거나 None 이외의 값을 반환하면 후속 오류 훅을 중단한다. 원래 처리 오류는 예외 체인에 보존하고 같은 오류 훅에 재귀 통지하지 않는다.
- Application의 라우팅·사전 검사 실패와 반환 이후 서버의 스트림 소비·전송 실패는 해당 RequestRunner 오류 훅의 대상이 아니다.
- [Response의 본문 정리 도우미](../../../src/Response.py)는 동일 객체 중복 정리를 방지하고, 응답 교체·body 변경 시 폐기 본문들을 모두 정리한다. 다른 응답으로 인계한 body는 미리 닫지 않는다.
- 정리 중 일부 실패가 있어도 나머지 본문 정리를 시도한다. 처리 오류가 이미 있으면 추가 정리 오류를 기록해 원래 예외를 보존하고, 단독 정리 실패는 전파한다.

### 3.4 계층별 순서

| 경로 | 응답 훅 순서 |
| --- | --- |
| 일반 핸들러 반환 | RequestRunner → Application |
| Extension 반환 | Extension → 내부 RequestRunner → Application |
| Extension 직접 출력 | 내부 RequestRunner의 전송 전 훅 → Extension 완료 훅 → Application 완료 훅 |

직접 출력의 응답 훅 이후 오류가 발생하면 아직 실행 중인 경계에서 오류를 관찰한다. Extension 안에서 호출한 writer 콜백이 실패한 경우 Extension → RequestRunner → Application 순서로 오류가 전파된다.

Application·Extension의 기존 Optional[Response] 완료 훅은 변경하지 않았다. [상위 명세](../2/REQUIREMENTS.md), [Application 명세](../4/REQUIREMENTS.md), [Extension 명세](../5/REQUIREMENTS.md)에 직접 출력 순서와 최신 계약을 보완했다.

## 4. 샘플과 로그

### 4.1 스트리밍 샘플

[Streaming.py](../../../samples/runners/Streaming.py)의 6개 핸들러에 세 훅을 모두 설정했다.

- `StreamingRequestLog`: `Sample.Streaming`의 INFO 로그로 요청 ID·메서드·URI 기록
- `StreamingResponseHeaders`: X-Request-ID 헤더 추가 및 INFO 응답 로그 기록
- `StreamingErrorLog`: ERROR 로그에 요청 정보·예외 메시지·traceback 기록

대상은 일반·chunked 입력과 출력, SSE, WebSocket이다. 응답 로그는 begin 또는 upgrade의 헤더 전송 전에 남는다.

### 4.2 일반 요청 샘플

[Requests.py](../../../samples/runners/Requests.py)의 GET·POST·PUT·DELETE·Upload 핸들러에 `RequestLog`, `ResponseLog`, `ErrorLog`를 연결했다. `Sample.Requests` 로거로 요청·응답은 INFO, 오류는 ERROR와 예외 정보를 기록한다.

로그의 경로별 차이는 다음과 같다.

| 경로 | 로그 순서 |
| --- | --- |
| 정상 응답 | 요청 훅 → 응답 훅 |
| run 실행 실패 | 요청 훅 → 오류 훅 |
| SSE 등 응답 시작 후 실행 실패 | 요청 훅 → 응답 훅 → 오류 훅 |
| RunRequest 내부 검증 실패 | 오류 훅만 실행 |
| 라우팅·Application 사전 검사 실패 | RequestRunner 훅 비호출 |

오류 훅을 보여주기 위해 정상 샘플에 강제 실패 옵션은 추가하지 않았다. 테스트에서 실패를 주입하거나 SSE 종료를 위한 예외를 발생시켜 로그와 원래 오류 전파를 검증했다.

## 5. 호환성 변경

| 제거한 계약 | 이전 방법 |
| --- | --- |
| RequestFilter | RequestRunnerRequest 구현 |
| ResponseFilter | RequestRunnerRequestResponse 구현 |
| onRequest | on_request 사용 |
| onResponse | on_request_response 사용 |
| `(Request, Optional[Response])` 조기 응답 튜플 | 지원 제거. 요청 훅은 Request만 반환 |
| writer의 기존 on_response 콜백 속성 | on_request_response 연결 사용 |

`on_error` 등 호환 별칭이나 자동 변환은 추가하지 않았다. 기존 필터 기반 테스트는 새 훅으로 이전하고, 폐기 API 거부 및 조기 응답 튜플 오류 테스트를 유지했다.

## 6. 주요 변경 파일

| 파일 | 내용 |
| --- | --- |
| [RequestRunner](../../../src/RequestRunner.py) | 세 ABC, 클래스 설정 검증·튜플 정규화, 필터 제거 |
| [공개 내보내기](../../../src/__init__.py) | 새 인터페이스 공개와 폐기 필터 제거 |
| [RunRequest](../../../src/Runners/RunRequest.py) | 실행·오류 경계, 응답 후처리 및 콜백 수명 관리 |
| [ResponseWriter](../../../src/IO/ResponseWriter.py) | 전송 전 콜백 실행, 직접 출력 제약 및 오류 자원 정리 |
| [Response](../../../src/Response.py) | 폐기 본문 중복 정리 방지·정리 오류 정책 |
| [Streaming 샘플](../../../samples/runners/Streaming.py), [Requests 샘플](../../../samples/runners/Requests.py) | 세 훅 연결 및 정상·오류 로그 |
| [집중 테스트](../../../tests/test_request_runner_hooks.py) | 계약·순서·오류·자원·전송·동시성 검증 |
| [샘플 테스트](../../../tests/test_samples.py) | 11개 핸들러의 로그·헤더·실패 전파 검증 |
| [핵심 테스트](../../../tests/test_core.py), [기능 테스트](../../../tests/test_features.py), [Application 훅 테스트](../../../tests/test_application_hooks.py) | 기존 필터 사용처와 기대값 이전 |
| [writer 테스트](../../../tests/test_writers.py), [WebSocket 테스트](../../../tests/test_websocket.py) | 전송 전 훅 및 프로토콜 제약 검증 이전 |

## 7. 검증 기록과 제약

기존 Windows·Python 3.14.5 editable 설치에서 프로젝트 소스를 대상으로 실행했다. 아래는 앞선 구현·샘플 수정 단계에서 실제 실행한 결과이며, 이번 기록 문서 작성 중 테스트를 재실행한 결과가 아니다.

| 시점 | 명령·검증 | 결과 |
| --- | --- | --- |
| 변경 전 기준선 및 기존 사용처 이전 | `python -m unittest test_core test_writers test_features test_application_hooks test_websocket -q` | 각각 63개 성공 |
| 핵심 구현 완료 | `python -m unittest test_request_runner_hooks -q` | 20개 성공 |
| 핵심 구현 완료 시 전체 회귀 | `python -m unittest discover -s . -p 'test_*.py' -v` | 총 218개: 213개 성공, 5개 skip |
| 핵심 구현 최종 형식 변경 후 | `python -m unittest test_request_runner_hooks test_exports -q` | 23개 성공 |
| 두 샘플에 세 훅 연결 완료 | `python -m unittest test_samples test_request_runner_hooks -q` | 33개 성공 |
| 정적·형식 검증 | 핵심 소스 및 샘플의 Pylance 진단, 새 테스트 구문 확인, `git diff --check` | 확인한 파일의 진단·구문 오류 및 공백 오류 없음 |

명령은 프로젝트의 테스트 디렉터리에서 실행했다. 샘플 테스트는 헤더 sender 시점에 요청·응답 로그가 이미 한 번씩 존재하고 본문은 아직 출력되지 않았음을 검사하며, 동일 요청 ID와 X-Request-ID 헤더 반영을 확인한다. 오류 로그의 예외 객체와 실제 전파 예외가 동일함도 확인한다.

- 전체 회귀 결과는 후속 샘플 로그 보강 이전 결과다. 최종 샘플 로그 변경 후에는 관련 33개 테스트를 실행했으며 전체 회귀를 재실행한 것으로 기록하지 않는다.
- 5개 skip은 Windows에서 실행할 수 없는 Gunicorn/POSIX 관련 검증이며 기존 POSIX CI 확인 대상으로 남긴다.
- 다른 Python 버전과 배포 산출물 빌드·설치 테스트는 로컬에서 수행하지 않았다.
- reader·writer의 데이터별 stream·SSE·WebSocket 확장 훅은 이번 구현 범위 밖이다.
