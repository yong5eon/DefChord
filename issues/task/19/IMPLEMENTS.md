# 구현 및 검증 기록

## 구현 내용

- [`docs/README.md`](../../../docs/README.md)와 [`docs/README.en.md`](../../../docs/README.en.md)에 설치, 라우팅, 입력 검증, 본문 읽기, 응답·스트리밍, Server-Sent Events, 확장, 서버 어댑터, 훅과 WebSocket 안내를 작성했다.
- 루트 [`README.md`](../../../README.md)와 [`README.en.md`](../../../README.en.md)를 프로젝트 소개, 설치, 빠른 시작과 매뉴얼 링크 중심으로 정리했다.
- 두 루트 README의 영어 서브타이틀과 슬로건을 원문 그대로 유지했다.
- [`README.setup.md`](../../../README.setup.md)를 패키지에서 독립적으로 읽을 수 있는 영어 소개·설치·빠른 시작 문서로 정리했다. 외부 링크는 추가하지 않았다.
- 제품 코드, API, 패키지 설정은 변경하지 않았다.

## 검증

- 이슈 기록·README·상세 매뉴얼 10개를 대상으로 Python 기반 Markdown 검사 스크립트를 실행했다. 로컬 링크와 앵커, 코드 펜스, Python 코드 블록 구문을 확인했고 오류가 없었다.
- `README.setup.md`의 외부 URL 여부를 검사했고 URL이 없었다.
- 한국어·영어 루트 README의 영어 서브타이틀과 슬로건 보존을 확인했다.
- `git diff --check`를 실행했고 오류가 없었다.
- 저장소 전체 테스트 스위트는 실행하지 않았다. 문서의 Python 코드 블록은 구문 검증했고, README 빠른 시작을 실제 기본 Python 서버에서 요청해 확인했다.

## 미완료 사항

- 선택형 Gunicorn·Uvicorn adapter의 실행 검증은 수행하지 않았다.

## 상세 매뉴얼 보강

- 기존 한 페이지 중심의 한국어·영어 매뉴얼을 소개/목차와 시작, 라우팅·요청, 응답·스트리밍, 확장·서버, 생명주기·오류, WebSocket 주제별 문서 쌍으로 재구성했다.
- 진입 문서에 DefEssential의 목적, 핵심 구성 요소, HTTP 요청 흐름과 단계별 학습 경로를 추가했다.
- 주제별로 라우팅과 데이터 검증, 콘텐츠 reader, 응답 객체와 file cleanup, 직접 스트리밍, SSE, 기본 extensions, server adapter 제약, hook 실행 순서, WebSocket 연결/메시지 계약을 보강했다.
- 실행·확인 가능한 예제 및 Mermaid 흐름도를 추가했다. 제품 코드, 공개 API, 패키지 설정은 변경하지 않았다.

### 추가 검증

- 이슈 기록과 문서를 포함한 Markdown 19개를 검사해 내부 링크와 제목 앵커, 코드 펜스 균형, 모든 Python 코드 블록 구문, PascalCase 파일명 및 한국어·영어 문서 쌍의 다이어그램 수 대응을 확인했다. 오류가 없었다.
- 문서의 경로·쿼리 변환 예제를 실제 `Application`에 등록해 직접 호출했고, `GET /values/12?count=3` 응답이 200 및 `{"value": 12, "count": 3}`임을 확인했다.
- `git diff --check`를 실행했고 오류가 없었다.
- 문서와 예제만 변경했으므로 전체 제품 테스트를 다시 실행하지 않았다. 기존 검증에서 기본 Python 서버 빠른 시작을 실행해 `GET /hello` 응답을 확인했으며, Gunicorn·Uvicorn 실행 검증은 여전히 미수행이다.

## Origin 및 인증 안내 상세화

- `RoutingAndRequests.md`와 `.en.md`에서 인증과 Origin 설명을 각각 독립된 절로 분리하고, 실제 `Auth`, `Authorization`, `Credentials`, `Origin` 및 CORS 구현에 맞춰 구성·검증 흐름과 제한사항을 상세히 설명했다.
- 인증 절에 Bearer 자격 증명 예제, 세션 사용, 필수·선택 인증의 차이, 실패 응답, 인증과 권한 검사의 구분 및 실제 토큰 검증 시 주의사항을 추가했다.
- Origin 절에 허용 목록 예제와 Origin 일치 기준, 누락·비허용 Origin 처리, preflight 검사, 응답 CORS 헤더와 `all=True`의 위험을 추가했다.
- Markdown 구조, Python 코드 블록 10개 구문, 로컬 파일 링크를 검사했고 모두 통과했다. `git diff --check`도 통과했다.
- 제품 코드와 공개 동작은 변경하지 않았다.

## 응답 훅과 인증 클래스 안내 보강

- 한국어·영어 라우팅 매뉴얼의 요청 흐름 다이어그램에 `RequestRunner.run` 이후 응답 훅을 추가하고, 그 다음 응답 처리·전송이 이뤄지도록 순서를 명시했다. 훅 실패 경로도 오류 응답 및 오류 훅으로 표시했다.
- 응답 훅이 일반 응답에서는 CORS 응답 헤더 적용과 전송 전에, 직접 출력에서는 응답 시작 시 실행되는 차이를 설명했다.
- 인증 안내에 `Query`, `Header`, `Cookie`, `HTTP`, `OAuth2Implicit`, `OAuth2Password`, `OAuth2ClientCredentials`, `OAuth2AuthorizationCode`를 모두 표로 소개하고 추출 위치와 동작, 생성자 예를 정리했다.
- OAuth2 클래스가 인증 흐름을 직접 수행하지 않고 Bearer 자격 증명 추출 및 OpenAPI 메타데이터를 제공한다는 구현 경계를 명시했다.
- Markdown 구조, Python 코드 구문, 링크 및 `git diff --check`를 검증했다.

## 일반 요청·응답과 스트리밍 문서 재구성

- 사용자 확정에 따라 일반 라우트·요청 검증·인증·Origin부터 JSON·텍스트·파일 응답까지를 `RoutingAndRequests` 한 문서에 연결했다.
- `StreamingAndWebSockets` 문서 쌍을 신설해 일반 입력 스트리밍, chunked 입력 스트리밍, 일반 출력 스트리밍, chunked 출력 스트리밍, SSE, WebSocket을 각각 설명했다.
- 기존 `ResponsesAndStreaming` 및 `WebSocket` 문서 쌍을 통합하고 제거했으며, 매뉴얼 목차와 학습 경로, Getting Started의 연결을 새 구조로 갱신했다.
- 제품 코드와 공개 API는 변경하지 않았다.
- 전체 `docs/` Markdown 문서의 로컬 링크, 코드 펜스, Python 구문을 검사했다. 일반·chunked 입력 리더와 일반·chunked 출력 writer, SSE 예제를 직접 실행해 기대한 bytes와 헤더를 확인했다.
- WebSocket 문서는 Python 구문 및 API 구현과 대조했으나 adapter를 통한 실제 연결 검증은 수행하지 않았다.

## 일반 응답 종류와 예제 보강

- 응답 문서에 기본 `Response`, `ResponseJSON`, `ResponseText`, `ResponseFile`을 구분하는 표를 추가했다.
- 기존에 설명으로만 언급했던 `ResponseText`의 상태 코드·헤더 지정 예제를 추가했다. 각 응답 클래스를 언제 사용할지 한국어·영어로 설명했다.
- 한국어·영어 문서의 Markdown 링크와 Python 코드 구문을 검사하고, `ResponseText` 예제가 반환하는 본문·헤더를 확인했다.

## 라우트 응답 훅 예제 추가

- 생명주기 매뉴얼의 route hook 예제를 요청 훅과 응답 훅을 함께 등록하는 예제로 확장했다.
- `RequestRunnerRequestResponse` 구현이 `Request`와 `Response`를 받고 응답을 반환하도록 보여주며, 요청 ID를 응답 헤더에 넣는 예제를 한국어·영어 문서에 추가했다.
- 응답 훅 실행 시점과 직접 출력 응답에서의 제약을 설명했다.
- Python 코드 구문, Markdown 링크와 `git diff --check`를 확인했다.

## 라우트·요청·응답 문서 제목 정리

- 일반 요청 흐름과 응답 클래스를 함께 다루는 내용에 맞춰 한국어 제목을 `라우트와 요청, 응답`, 영어 제목을 `Routes, Requests, and Responses`로 변경했다.
- 매뉴얼 목차와 Getting Started의 관련 링크 문구를 새 제목에 맞췄다.
- 내부 링크와 Markdown 구조를 확인하고 `git diff --check`를 실행했다.
