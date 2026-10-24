# 로깅 지원 구현 기록

## 1. 개요

[로깅 지원 이슈](./ISSUE.md)와 [요구사항 명세서](./REQUIREMENTS.md)에 따라 프레임워크 로그를 `DefEssential` 계층으로 정리하고 주요 실행 경로의 로그를 보강했다.

DefStream처럼 Python 표준 `logging`으로 로그를 기록하며, 출력 설정은 샘플의 Application 시작 훅에서 담당한다. 이 문서는 2026-10-25 기준 최종 구현과 앞선 구현 작업에서 확인한 검증 결과를 기록한다.

## 2. 최종 구현 방식

- 클래스는 `logger = getLogger('DefEssential.…')`로 고정 이름을 선언하고 메서드에서 직접 사용한다.
- 공통 함수는 담당 경계의 모듈 로거를 사용한다. 로거를 전달하기 위한 공개 인자는 추가하지 않았다.
- 사용자 하위 클래스는 기존 로거를 상속하며 필요하면 명시적으로 재정의할 수 있다.
- 라이브러리는 핸들러·포매터·필터·레벨을 설정하거나 기존 사용자 설정을 제거하지 않는다. `basicConfig()`와 `NullHandler`도 추가하지 않았다.
- 로깅 때문에 공개 훅 계약이나 요청·응답 처리 순서를 바꾸지 않는다.

### 2.1. 후속 검토에 따른 단순화

초기 구현의 로깅 전용 구조를 다음과 같이 제거했다.

- 단계 로그용 `stage()` context manager와 자동 단계별 타이머를 제거하고 처리 지점의 직접 logger 호출로 바꿨다.
- 라우트·어댑터 전달용 `REQUEST_ROUTE`, `SERVER_ADAPTER` ContextVar와 설정·해제 코드를 제거했다.
- 클래스명·문자열 처리 함수도 표준 Python 속성과 표현으로 대체하고 별도 로깅 유틸 파일을 삭제했다.

라우트는 Application의 등록·선택 지점에서, 어댑터는 각 서버의 생명주기 지점에서 기록한다. 요청 실행 단계와 HTTP 전송 결과는 지역 변수로 관리하며 로깅용 공유 상태를 두지 않는다.

## 3. 기록 범위와 레벨

| 대상 | 로거 | 구현 내용 |
| --- | --- | --- |
| [Application](../../../src/Application.py) | `DefEssential.Application` | 시작·종료, 확장 연결·롤백·정리, 라우트 등록·선택, 훅 실행과 디스패치 |
| [요청 실행기](../../../src/Runners/RunRequest.py) | `DefEssential.RequestRunner` | 인증·검증·본문 처리·핸들러 생성·실행, 요청·응답·오류 훅과 직접 출력 단계 |
| [확장 실행기](../../../src/Runners/RunExtension.py) | `DefEssential.Extension` | 확장 호출과 요청·응답·오류 훅 |
| [공통 요청 처리기](../../../src/Adapter/RequestHandler.py) | `DefEssential.Server` | HTTP 수신, 오류 응답 선택, 최종 전송 결과와 본문 정리 실패 |
| [Python](../../../src/Adapter/Implements/Python/Server.py)·[Gunicorn](../../../src/Adapter/Implements/Gunicorn/Server.py)·[Uvicorn](../../../src/Adapter/Implements/Uvicorn/Server.py) 서버 | `DefEssential.Server` | 어댑터 식별, 실제 바인딩 후 준비 완료, 시작·종료·실패 |
| [WebSocket](../../../src/IO/WebSocket/WebSocket.py) | `DefEssential.IO.WebSocket` | 연결 상태, 종료 코드, 프로토콜 위반과 내부 실패 |
| [내장 확장](../../../src/Extensions) | `DefEssential.Extensions.*` | File·FileSystem·Ping·Metrics·Status·Specifications·Swagger의 주요 처리와 실패 |

| 레벨 | 기록 기준 |
| --- | --- |
| DEBUG | 등록·선택, 검증·실행·훅의 진입과 완료, 정상 분기 및 관찰 정보 |
| INFO | 애플리케이션·서버 생명주기, HTTP 전송 결과 요약 |
| WARNING | 클라이언트 연결 단절, WebSocket 프로토콜 위반 |
| ERROR | 예상하지 못한 내부 오류, 시작·전송·정리 실패 |

일반적인 4xx 응답이라는 이유만으로 WARNING이나 ERROR로 승격하지 않는다. 실패한 단계 뒤에 정상 완료 로그를 남기지 않으며, 샘플의 훅 관찰 로그는 DEBUG로 구분한다.

## 4. 요청 처리와 오류 경계

### 4.1. 단계 로그

[RunRequest](../../../src/Runners/RunRequest.py)는 기존 실행 흐름 안에서 직접 로그를 기록한다. 지역 `phase` 값으로 실패 단계를 식별하고, 실제 호출이 끝난 뒤에만 완료를 기록한다. 로깅만을 위한 별도 실행 래퍼는 두지 않았다.

### 4.2. HTTP 전송 결과

[공통 요청 처리기](../../../src/Adapter/RequestHandler.py)는 요청별 전송 요약을 INFO로 한 번 기록한다.

| 항목 | 의미 |
| --- | --- |
| `request_id` | 서버 경계에서 생성한 최초 요청의 ID. 생성 전 실패하면 `None` |
| `method` | 앞 32자를 `ascii()`로 이스케이프한 메서드. 요청 생성 전에는 `None` |
| `status` | writer가 실제 응답을 시작한 경우의 상태. 시작 전에는 `None` |
| `outcome` | `completed`, `failed`, `disconnected` |
| `duration` | 공통 처리 진입부터 전송 결과 기록 직전까지 `monotonic()`으로 측정한 초 단위 시간 |

요약에는 원시 요청 경로·쿼리, 라우트나 어댑터 전달용 상태를 추가하지 않았다.

- 반환 응답 전송 또는 직접 출력 종료를 확인한 경우에만 `completed`로 기록한다.
- 쓰기·flush·iterable 소비 실패는 성공으로 처리하지 않는다. 연결 단절은 `disconnected`로 구분한다.
- 핸들러·응답 훅 완료는 실제 전송 완료가 아니다. 101 업그레이드 역시 WebSocket 세션 전체의 성공을 뜻하지 않는다.
- 전송 요약 뒤의 본문 정리 실패는 별도 ERROR로 기록한다. 전송 시간에는 이 후속 정리 시간이 포함되지 않는다.
- Python 기본 HTTP 처리기의 헤더 생성 시점 접근 로그는 DEBUG로 구분해 INFO 요약과 중복되지 않게 했다.

### 4.3. 예외 처리

- 프레임워크의 HTTP 오류는 기존 오류 응답으로 변환한다.
- 응답 시작 전 예상하지 못한 예외는 최종 서버 경계에서 ERROR와 traceback을 기록하고 기존 500 응답으로 처리한다.
- 응답 시작 후 실패는 두 번째 오류 응답을 보내지 않고 기록 후 전파한다.
- 연결 단절은 WARNING으로 기록하며 예외 문자열과 traceback을 반복 출력하지 않는다.
- 중간 실행 계층과 샘플 훅은 같은 전파 예외의 traceback을 중복 기록하지 않는다. 독립적인 정리 실패는 별개 사건으로 기록한다.

## 5. 샘플 출력 설정과 기록 제한

[샘플](../../../samples/Sample.py)의 `LoggingSetup`을 첫 Application 시작 훅으로 등록했다.

- 루트 레벨을 DEBUG로 설정하고 이름이 `Sample`인 콘솔 핸들러를 추가한다.
- 핸들러의 출처 필터로 `Sample`·`Sample.*`, `DefEssential`·`DefEssential.*`만 선택한다. 유사 접두 이름과 외부 서버 로거는 제외한다.
- 같은 이름의 핸들러는 재시작 시 중복 추가하지 않으며 기존 사용자 핸들러는 제거하지 않는다. 다른 핸들러의 출력까지 제한하지는 않는다.
- 현재 포맷은 `%(asctime)s %(levelname)-8s %(name)s %(message)s`이며 밀리초와 레벨별 색상을 표시한다. 색상 포매터는 LogRecord 복사본을 사용한다.
- 시작 훅 이전의 구성·등록 로그를 소급 출력하지 않으며 기존 시작 배너는 유지한다.
- [일반 요청](../../../samples/runners/Requests.py)·[스트리밍](../../../samples/runners/Streaming.py) 샘플의 훅 로그는 DEBUG로 기록한다.

기본 문맥에서 원시 URI·경로·query, 인증정보, 요청·응답 본문, WebSocket payload·close reason을 제외했다. Application은 선택된 등록 라우트의 앞 256자를 `ascii()`로 이스케이프해 기록한다. 이 길이는 이스케이프 전 문자 수 기준이다.

traceback에는 예외 메시지와 소스 줄이 포함될 수 있으므로 완전한 비밀정보 차단을 보장하지 않는다. 사용자 예외 메시지와 등록 라우트에 민감정보를 넣지 않아야 하며, 추가 필터링은 애플리케이션 설정의 책임이다.

## 6. 검증 기록

아래는 최종 코드 단순화 후 수행한 검증 결과다. 이번 문서 작성 중 테스트를 다시 실행한 결과는 아니다.

- Windows의 Python 3.12에서 작업 트리 소스를 직접 로드해 전체 `unittest` 발견 테스트를 실행했다.
- 총 **243개 중 238개 통과, 5개 건너뜀**을 확인했다. 설치된 별도 패키지를 대상으로 한 결과가 아니다.
- [로깅 전용 테스트](../../../tests/test_logging.py) 21개로 로거 상속·재정의, 설정 비간섭, 단계·레벨, 전송 요약, 실패·단절·정리, 병렬·중첩 요청, 민감정보 제외, 샘플 설정의 중복 방지를 검증했다.
- 기존 훅·writer·스트리밍·SSE·WebSocket 회귀와 Python·Uvicorn의 실제 HTTP 전송을 포함했다.
- 포트 0의 실제 준비 완료 로그, Uvicorn의 실제 바인딩 실패, Python 바인딩 실패의 테스트 더블 검증을 포함했다.
- 소스·샘플·테스트의 Python 3.9 구문 분석과 `git diff --check`를 통과했다. 주요 변경 파일의 Pylance 타입 오류도 확인했다.
- 로깅 유틸 파일 삭제와 잔여 import·호출 제거를 확인했다.

### 환경 제약

- 건너뛴 5개는 POSIX가 필요한 Gunicorn 실행·전송 적합성 테스트다. 실제 Gunicorn 실행은 Linux·WSL 또는 CI에서 추가 확인해야 한다.
- Python 3.9는 구문 분석만 수행했다. 해당 버전의 실제 런타임 테스트를 통과한 것으로 간주하지 않는다.
- 라이브러리 미설정 시 표준 `logging.lastResort` 동작을 유지한다. Gunicorn·Uvicorn 자체 로깅 설정과 외부 접근 로그의 출력 정책은 별도로 관리해야 한다.

## 7. 관련 문서

- [요구사항 명세서](./REQUIREMENTS.md)
- [변경 로그](./README.md)
