# RequestRunner 생명 주기 훅 작업 계획서

## 1. 목표와 상태

[요구사항 명세서](./REQUIREMENTS.md)에 따라 RequestRunner의 기존 필터를 요청·응답·오류 훅으로 대체한다. 아래 구현·샘플·테스트 이전을 완료했으며 실제 검증 결과와 환경 제약은 7절에 기록한다.

핵심은 기존 실행 구조를 유지하면서 응답 후처리를 재사용하는 것이다.

- `on_request`: 검증·본문 처리·인스턴스 생성 후 `run()` 직전 실행
- `on_request_response`: Response 반환 시 RunRequest에서 실행하거나, 직접 출력 시 ResponseWriter에 주입한 콜백으로 헤더 전송 전에 실행
- `on_request_error`: RunRequest 진입부터 결과 반환까지 경계 안의 Exception 관찰

stream 입출력의 데이터별 제어, SSE 이벤트·WebSocket 메시지별 훅, 범용 플러그인 및 `__init_subclass__` 확장 시스템은 추가하지 않는다.

## 2. 구현 기준

| 항목 | 적용 기준 |
| --- | --- |
| 공개 계약 | `RequestRunnerRequest`, `RequestRunnerRequestResponse`, `RequestRunnerRequestError` |
| 클래스 선언 인자 | `on_request`, `on_request_response`, `on_request_error` |
| 입력 정규화 | 단일 인터페이스 인스턴스·Sequence·None을 검증하고 튜플로 보관 |
| 실행 순서 | 복수 훅은 입력 순서, 중간 실패 시 같은 이벤트의 후속 훅 중단 |
| 요청 반환 | Request만 허용하며 조기 응답 튜플 제거 |
| 응답 반환 | Response만 허용하며 직접 출력에서도 헤더용 Response 사용 |
| writer 의존성 | RequestRunner를 참조하지 않고 `Response -> Response` 콜백만 호출 |
| 오류 | 관찰 후 원래 오류 전파, 오류 훅 실패 시 원래 오류를 예외 체인에 보존 |
| 호환성 | 기존 필터·인자·별칭 제거, 훅 미설정 처리와 전송 안전성 유지 |

## 3. 단계별 작업

### 1단계: 공개 선언 계약과 설정 이전

대상: [RequestRunner](../../../src/RequestRunner.py), [패키지 내보내기](../../../src/__init__.py)

- 세 ABC 인터페이스와 `__call__` 시그니처를 정의하고 공개한다.
- RequestProperties와 `__init_subclass__`를 새 인자·이벤트별 튜플 저장 방식으로 바꾼다.
- 단일·복수·None·생략을 처리하고 문자열·잘못된 원소·일반 함수·인터페이스 클래스·지원하지 않는 iterable을 선언 시 거부한다.
- 다른 설정에 사용 중인 기존 계약 검증은 보존한다. 훅 정규화는 기존 패턴을 재사용하되 관련 없는 구성요소까지 리팩터링하지 않는다.
- 부모 훅을 자동 병합하지 않고 하위 클래스에서 명시한 설정만 사용한다. 입력 시퀀스 복사와 클래스 간 격리를 검증한다.
- RequestFilter·ResponseFilter와 `onRequest/onResponse`의 선언·export를 제거한다. 호환 별칭은 추가하지 않는다.

완료 조건: AC-01~AC-03의 선언·내보내기 검증 통과. 기존 필터를 참조하는 테스트·샘플은 4단계에서 이전하며, 그 전의 전체 테스트 수집 실패를 최종 검증 결과로 취급하지 않는다.

### 2단계: RunRequest의 실행·오류 경계 변경

대상: [RunRequest](../../../src/Runners/RunRequest.py), [CORS](../../../src/CrossOriginResourceSharing.py), [Response](../../../src/Response.py)

- 기존 CORS 원본 → 인증 → 파라미터 → 쿼리 → 헤더 → 본문 → 생성 순서를 보존한다.
- 생성 후 요청 훅을 실행하고 마지막 유효 Request를 보관한다. 반환 Request를 다음 훅·`run()`·응답 및 오류 훅에 전달한다.
- 요청 교체로 라우팅·검증·본문 처리를 다시 수행하지 않는다.
- 기존 응답 필터 후처리를 새 응답 훅 → CORS의 공통 후처리로 바꾼다. 일반 Response 반환 경로와 writer 주입 경로가 같은 함수를 사용하게 한다.
- `run()` 반환값과 writer 시작 상태를 검사한다. 직접 출력 없는 None 및 직접 출력과 Response 동시 반환은 기존처럼 오류로 처리한다.
- RunRequest 내부 검증부터 후처리·writer 종료까지 Exception을 오류 관찰 경계로 묶는다. 정상 완료한 단계나 훅을 실패 시 반복하지 않는다.
- 오류 훅의 잘못된 반환·예외는 후속 오류 훅을 중단하고 원래 오류를 예외 체인에 보존한다. 오류 훅을 재귀 호출하지 않는다.
- 응답 교체·body 교체·동일 body 인계·처리 실패 시 폐기 자원을 정리한다. 정리 실패가 원래 처리 예외를 가리지 않도록 명세의 기록·전파 정책을 적용한다.

완료 조건: AC-04~AC-06, AC-09~AC-12의 실행 순서·실패·자원 검증 통과.

### 3단계: ResponseWriter 콜백 연결과 직접 출력 검증

대상: [ResponseWriter](../../../src/IO/ResponseWriter.py), [RunRequest](../../../src/Runners/RunRequest.py), [공통 요청 처리기](../../../src/Adapter/RequestHandler.py)

- 기존 writer 응답 콜백 연결 지점을 활용한다. 새 등록 관리자나 전송 방식 감지 계층은 만들지 않는다.
- 요청 훅 완료 후 최종 Request의 writer에 요청별 후처리 콜백을 연결하고 `run()`을 실행한다.
- `begin()`과 `upgrade()`가 헤더를 보내기 전에 주입된 후처리를 호출하도록 한다.
- 반환 Response는 RunRequest에서 후처리하며 서버의 기존 `filtered=True` 경로로 재실행을 방지한다.
- 직접 출력 후 `run()` 반환·writer 종료에서 응답 훅을 다시 실행하지 않는다.
- 정상·실패 모두 실행 경계 종료 시 주입한 콜백을 해제한다. 같은 writer를 통해 서버 오류 응답이 생성되는 경우에도 폐기된 콜백이 재호출되지 않게 한다.
- 본문이 빈 bytes인지, Content-Length가 없는지, WebSocket이 101을 유지하는지 후처리 이후 검증한다. 헤더 시작·중복 begin·전송 실패 상태와 CORS를 보존한다.
- 콜백 실패가 헤더 전송 전이면 서버의 기존 오류 응답 정책을 따르고, 헤더 전송 후 출력 실패면 새 오류 응답을 보내지 않는다.
- `run()` 안에서 응답 훅 실행 뒤 쓰기·flush·종료가 실패하는 경우 오류 훅이 이어서 실행될 수 있음을 검증한다.

출력별 연결 확인 대상:

| 경로 | 연결 지점 | 확인 내용 |
| --- | --- | --- |
| [StreamWriter](../../../src/IO/Writers/StreamWriter.py) | `ResponseWriter.begin()` | 헤더 전 훅, 이후 본문 쓰기 |
| [ChunkedStreamWriter](../../../src/IO/Writers/ChunkedStreamWriter.py) | 상속한 begin 경로 | chunk마다 훅을 호출하지 않음, 프레이밍 보존 |
| [SSE writer](../../../src/IO/Writers/ServerSentEventsWriter.py) | 내부 StreamWriter의 begin | 첫 이벤트 전에 훅 실행, 종료를 기다리지 않음 |
| [WebSocket](../../../src/IO/WebSocket/WebSocket.py) | accept에서 writer upgrade로 연결 | handshake 응답에 한 번 적용, 프레임별 호출 없음 |
| 반환 iterable Response | RunRequest 반환 후처리 | 본문을 소비하지 않고 반환, 서버 전송에서 중복 없음 |

상위 writer 래퍼가 이미 공통 경로를 사용하면 래퍼별 코드를 불필요하게 변경하지 않는다.

완료 조건: AC-07~AC-08, AC-14 및 콜백 해제·오류 응답 비재적용 검증 통과.

### 4단계: 사용처·샘플·계층 통합 이전

대상: [샘플](../../../samples/Sample.py), [스트리밍 샘플](../../../samples/runners/Streaming.py), 기존 필터 관련 테스트

- 기존 RequestFilter·ResponseFilter 구현과 클래스 인자를 새 인터페이스·인자로 이전한다.
- 조기 응답 테스트는 새 요청 훅에서 튜플을 거부하는 검증으로 바꾼다. 별도의 기존 CORS 회귀는 조기 응답에 의존하지 않는 경로에서 유지한다.
- 이전에 필터가 제거됐음을 확인하는 테스트와 실제 필터 사용 테스트를 구분하고, 다른 구성요소의 `on_request_response` 계약을 잘못 변경하지 않는다.
- 스트리밍 샘플의 reader·writer 사용 방식은 유지한다. 훅 예제를 보완한다면 SSE 무한 실행 종료를 기다리지 않고 begin에서 응답 훅이 실행되는 점을 보여준다.
- [Extension 실행기](../../../src/Runners/RunExtension.py)의 내부 RequestRunner 경유, 일반 핸들러 및 다른 Extension과의 호출 격리를 확인한다.
- Application·Extension의 기존 요청·응답·오류 훅은 유지하고 내부 RequestRunner에 해당 훅을 복사해 등록하지 않는다.
- [상위 명세](../2/REQUIREMENTS.md), [Application 명세](../4/REQUIREMENTS.md), [Extension 명세](../5/REQUIREMENTS.md)에 이번 계약 참조와 직접 출력 순서 차이를 필요한 범위에서 반영한다. 변경 전 조사 기록은 보존한다.
- 요구사항의 구현 상태와 검증 기록은 실제 수행 결과에 맞춰 갱신한다.

완료 조건: AC-13, AC-15~AC-16 및 영향받는 사용처의 테스트 수집·실행 통과.

### 5단계: 집중·회귀 검증과 완료 판정

1~4단계는 위 순서로 진행하되, 각 단계의 집중 테스트는 구현과 함께 추가한다. 전체 공개 API·사용처 이전이 끝난 뒤 관련 테스트를 묶어 실행한다.

실패 시 변경으로 인한 문제와 기존 문제를 구분하고, 이번 변경에 직접 연결된 원인을 수정한 뒤 해당 검증을 재실행한다. 관련 없는 선행 문제까지 수정하지 않는다.

완료 조건: 4절의 AC 매핑을 모두 충족하고 테스트 결과와 남은 제약을 기록한다.

## 4. 테스트 설계와 수용 기준 매핑

새 [집중 테스트 모듈](../../../tests/test_request_runner_hooks.py)을 추가한다. 기존 unittest 관례를 따르고, 현재 [핵심 테스트](../../../tests/test_core.py)와 [writer 테스트](../../../tests/test_writers.py)의 요청·전송 구성 방식을 재사용한다.

| 검증 묶음 | 핵심 검증 | 수용 기준 |
| --- | --- | --- |
| 선언 계약 | 단일·복수·None·복사·상속·잘못된 입력·export | AC-01~AC-03 |
| 실행 파이프라인 | 검증 순서, 요청 교체, run 직전 호출, 조기 응답 튜플 거부 | AC-04~AC-05 |
| 응답 후처리 | 수정·교체·잘못된 반환, CORS 적용 순서 | AC-06 |
| 직접 출력 | begin·upgrade·SSE의 헤더 전 호출, 헤더 변경 실제 반영, 중복 방지, 콜백 해제 | AC-07~AC-08 |
| 오류와 경계 | 검증·본문·생성·훅·run·출력·종료 실패, 오류 훅 순서·중단·체인 | AC-09~AC-10, AC-12 |
| 본문 자원 | 폐기·교체·공유 body의 close 횟수, 정리 오류 기록·전파 | AC-11 |
| 계층 통합 | 일반 반환과 Extension 직접 출력의 서로 다른 응답 훅 순서, 비대상 훅 비호출 | AC-13 |
| 전송 경계 | 반환 iterable 미소비, 반환 후 전송 실패 비통지, run 안 출력 실패 통지 | AC-14 |
| 회귀와 이전 | 훅 미설정, 동시 요청 격리·객체 공유, 폐기 API 거부·샘플 이전 | AC-15~AC-16 |

검증 도구는 다음처럼 작게 구성한다.

- 이벤트 목록으로 요청 훅·run·응답 훅·헤더 sender·본문 쓰기 순서와 횟수를 비교한다.
- 읽기 시점을 기록하는 reader로 on_request가 전체 업로드를 기다리지 않는지 확인한다.
- 종료 가능한 SSE·WebSocket 테스트 흐름으로 호출 시점을 확인한다. 무한 루프 샘플을 그대로 테스트 실행하지 않는다.
- close 카운터와 오류를 발생시키는 본문으로 자원 소유권·예외 보존을 확인한다.
- 전송 실패 위치를 헤더 전·헤더 전송·본문 쓰기·flush·종료·반환 후 소비로 구분한다.
- 동시 요청은 결정적인 동기화 수단으로 겹치게 하고, 임의 sleep에 의존해 통과 여부를 판단하지 않는다.

## 5. 실행할 검증 명령

실행 전 사용할 Python이 변경한 소스에 연결된 DefChord을 가져오는지 확인한다. 오래된 설치 패키지에 테스트를 실행해 통과한 결과를 사용하지 않는다. 아래는 검증 명령 예시이며 실제 작업 디렉터리와 실행 결과는 7절을 따른다.

### 집중 검증

```powershell
python -m unittest discover -s tests -p test_request_runner_hooks.py -v
```

### 영향 범위 회귀

테스트 디렉터리가 import 경로에 들어가도록 이동해 관련 모듈을 한 runner에서 실행한다.

```powershell
Push-Location tests
try {
  python -m unittest test_request_runner_hooks test_core test_features test_writers test_sse test_websocket test_application_hooks test_extension_hooks test_extensions test_builtin_factories test_files test_exports test_samples test_transport_conformance -v
} finally {
  Pop-Location
}
```

새 의존성·린터는 추가하지 않는다. 선택한 검증에서 패키지나 도구 누락이 확인된 경우에만 기존 의존성 구성에 따라 복원한다.

### 최종 회귀

공개 API 제거가 여러 테스트와 어댑터에 영향을 주므로 통합 이전 완료 후 기존 [CI](../../../.github/workflows/ci.yml)의 unittest 전체 검증을 실행한다.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

배포 산출물 검증은 기존 CI의 빌드·설치 패키지 테스트 경로를 따른다. 로컬 집중 검증마다 재설치·배포 빌드를 반복하지 않는다. 선택 의존성·운영체제 때문에 건너뛴 어댑터 테스트는 통과한 것으로 기록하지 않고 CI 확인 범위를 남긴다.

## 6. 주요 위험과 대응

| 위험 | 대응 |
| --- | --- |
| 반환 응답과 writer에서 이중 후처리 | 공통 후처리 함수 재사용, 서버 filtered 경로 유지, 호출 횟수 검증 |
| 실패 후 서버 오류 응답에 콜백 잔존 | 실행 경계의 finally에서 연결 해제, 실제 오류 응답 경로 검증 |
| 직접 출력 응답 훅을 완료 이벤트로 오해 | 전송 전 이벤트임을 문서화하고 이후 출력 오류 통지 테스트 |
| 직접 출력에서 Extension과 응답 훅 순서 변경을 놓침 | 반환·직접 출력 통합 테스트 분리, 연관 명세 최신 계약 보완 |
| 요청 교체로 reader·writer·본문 유실 | 자동 보정하지 않음, 사용자 보존 책임과 최종 Request 연결 검증 |
| 응답 교체가 공유 body를 조기 close | body 소유권 기준으로 정리하고 close 횟수 테스트 |
| 폐기 API 테스트를 삭제하며 회귀도 소실 | 의도적 조기 응답 제거와 유지할 CORS·출력·검증 테스트를 분리해 이전 |

## 7. 완료 체크리스트와 검증 기록

- [x] 세 공개 훅과 클래스 설정·내보내기를 이전했다.
- [x] run 직전 요청 훅과 전체 실행 경계의 오류 관찰을 구현했다.
- [x] 응답 반환·begin·upgrade가 공통 응답 후처리를 사용한다.
- [x] 콜백 중복 실행·잔존과 응답 자원 누수를 방지했다.
- [x] 일반·chunked·SSE·WebSocket과 계층 통합을 검증했다.
- [x] 샘플·기존 테스트·상위 및 연관 문서를 최신 계약으로 이전했다.
- [x] 16개 수용 기준과 관련 회귀 결과를 기록했다.

### 검증 결과

Windows의 기존 Python 3.14.5와 editable 설치를 사용했다. 테스트 디렉터리에서 가져온 DefChord이 프로젝트의 소스 진입점을 가리킴을 확인했다. 의존성 추가·재설치 없이 검증했다.

| 검증 | 실제 명령·방법 | 결과 |
| --- | --- | --- |
| 변경 전 기준선 | 테스트 디렉터리에서 `python -m unittest test_core test_writers test_features test_application_hooks test_websocket -q` | 63개 성공 |
| 기존 사용처 이전 | 동일한 집중 명령 | 63개 성공 |
| 새 훅 계약 | 테스트 디렉터리에서 `python -m unittest test_request_runner_hooks -q` | 20개 성공 |
| 최종 전체 회귀 | 테스트 디렉터리에서 `python -m unittest discover -s . -p 'test_*.py' -v` | 218개 중 213개 성공, 5개 skip, 실패·오류 없음 |
| 정적 확인 | Pylance의 변경 핵심 소스 진단 및 새 테스트 구문 확인 | 오류 없음. 새 테스트 진단은 미사용 매개변수 힌트만 존재 |
| 형식·변경 확인 | `git diff --check`, 제거한 API 사용처 검색 | 공백 오류 없음. 폐기 API 이름은 거부·제거 검증에만 남음 |

5개 skip은 Gunicorn/POSIX 및 관련 worker 검증이다. Windows에서 실행하지 못한 항목을 통과로 집계하지 않았으며 기존 CI의 POSIX 검증 대상으로 남긴다. 배포 산출물 빌드·설치 테스트와 다른 Python 버전의 실행은 이번 로컬 검증에서 수행하지 않았다.

집중 테스트 작성 중 입력 스트림에 필요한 Content-Type 누락과 서버 OSError의 로그 수준 기대값을 수정했고, 테스트 삽입 중 발생한 들여쓰기 오류를 제거했다. 응답 교체 시 원래 본문의 정리가 실패해도 중간·최종 본문 정리를 누락하지 않도록 공통 본문 정리를 보완하고 close 횟수 회귀 테스트를 추가했다. 위 결과는 이 수정들을 반영한 최종 실행 결과다.

reader·writer의 데이터별 추가 훅은 범위 밖으로 유지한다. Application·Extension의 완료 훅은 기존 Optional[Response] 계약을 유지하고, 이번 RequestRunner 응답 훅만 헤더 전송 전 Response 변환 계약을 사용한다.
