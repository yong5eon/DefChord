# HTTP 샘플

Liquirizia.WSGI의 HTTP 시나리오를 단일 `RequestRunner`, `run(request)`, Readers·Writers 및 Application별 등록 방식으로 이전했다. WSGI, Liquirizia, Swagger UI 설치는 필요하지 않다.

## 실행

일반 요청 처리 클래스는 `app.add(RunExample)`로 등록하고, 확장은 `Application(exts=(...))`로 등록한다.

Swagger 확장은 `Swagger('/swagger', spec_uri='/api/doc')`처럼 명세 URI를 필수로 지정한다. `spec_uri`는 `/`로 시작하는 동일 출처 경로이며, `Specifications` 확장 자동 탐색이나 개수 제한 없이 해당 주소의 OpenAPI 문서를 사용한다.

Status 확장도 `Status('/status', metrics_uri='/metrics')`처럼 동일 출처의 메트릭 URI를 필수로 지정하며, `Metrics`를 직접 참조하거나 자동 탐색하지 않는다. Status는 HTML만 제공하고 브라우저가 지정한 URI에 `Accept: application/json`으로 요청한다. Metrics는 해당 헤더가 있으면 JSON 스냅샷을, 그 외에는 기존 Prometheus 텍스트를 반환한다.

DefEssential를 설치했거나 개발용 import 경로가 연결된 환경에서 DefEssential 프로젝트 디렉터리를 기준으로 실행한다.

```powershell
python -m samples.Sample
```

브라우저에서 `http://127.0.0.1:8000/`에 접속한다. 기본 로깅을 사용하며 `Ctrl+C`로 종료한다. `create_application()`을 호출할 때마다 라우터·파일 연결은 독립적으로 생성된다. 샘플 리소스 경로는 실행 디렉터리가 아닌 소스 위치를 기준으로 계산한다.

`Ctrl+C`로 서버 실행 루프를 중단하면 traceback 없이 확장을 역순으로 종료하고 `with serve(...)` 블록을 빠져나오면서 수신 소켓을 닫는다. 정리 중 발생한 오류는 숨기지 않는다. 실행 중인 요청 스레드는 기존 daemon 정책을 따르며, 무한 스트림의 완료를 기다리는 종료 방식은 아니다.

시작 출력의 `Applications` 목록과 개수는 확장 라우트를 제외한 `RequestRunner` 등록만 대상으로 한다. 표시 이름은 클래스 선언의 `name=`으로 지정할 수 있다. 예를 들어 `class RunExample(RequestRunner, method='GET', url='/example', name='Example')`처럼 선언한다. 생략하면 기존 클래스 이름을 표시한다. `File`, `FileSystem`을 포함한 확장은 `Extensions` 목록에만 확장 클래스 이름과 호스트 없는 등록 경로로 표시한다.

파일 제공도 `Application(exts=(...))`로 등록한다. 단일 파일은 `File('/favicon.ico', 파일경로)`, 디렉터리는 `FileSystem('/css', Connection(Configuration(디렉터리경로)))`로 연결한다. `add_file`, `add_files`, `add_file_system_object`는 제거했다. 기존 `add_files`와 달리 FileSystem은 요청 시 파일을 조회하므로 등록 이후 생성한 파일도 제공한다. 두 확장은 GET·HEAD와 `onRequest`·`onResponse` 필터를 지원한다. FileSystem 연결은 애플리케이션 시작 시 `connect()`, 종료 시 `close()`를 호출하며 중첩 접두사 우선순위와 로컬 파일시스템의 경로 접근 제한을 유지한다. 다른 확장과 마찬가지로 리소스 경로는 OpenAPI 명세에서 제외된다.

## 이전 대응표

인증·본문 검증 샘플은 `RunFactory`를 상속한 `RunAuthFactory`와 `RunContentFactory`로 처리 클래스를 생성한다. 시작 출력에는 내부 클래스 경로 대신 `RunAuth(query)`, `RunAuth(oauth2/implicit)`, `RunContent(integer)`처럼 지정된 이름을 표시한다.

| 기존 시나리오 | 현재 구현 | 경로·동작 |
| --- | --- | --- |
| `Request/RunGet`, `RunPost`, `RunPut`, `RunDelete` | [Requests.py](Requests.py) | `/api/run/:a/:b`, 경로·쿼리·JSON 검증과 기존 계산식 |
| `Request/RunUpload` | [Requests.py](Requests.py) | POST `/api/run/upload`, Content-Format·Content-Charset에 맞춰 바이너리 반환 |
| `ContentValidation/RunContent*` | [ContentValidation.py](ContentValidation.py) | POST `/api/content/bool`, `integer`, `number`, `string`, `array`, `object` |
| `Auth/RunAuth*` | [Authentication.py](Authentication.py) | Query·Header·Cookie·HTTP와 네 OAuth2 흐름 인증 |
| `Auth/*Token` | [Authentication.py](Authentication.py) | 기존 토큰 요청 경로·쿼리·폼 처리 |
| `Request/RunStreamIn`, `RunStreamOut` | [Streaming.py](Streaming.py) | PUT·GET `/api/run/stream` |
| `Request/RunChunkedStreamIn`, `RunChunkedStreamOut` | [Streaming.py](Streaming.py) | PUT·GET `/api/run/stream/chunked` |
| `Request/RunServerSentEvent` | [Streaming.py](Streaming.py) | GET `/api/run/stream/sse`, 무한 이벤트·ID·retry |
| `RunStatus`, `RunOptions` | [Sample.py](Sample.py) | `/status`, `/options?p=/status` 및 실제 OPTIONS |
| `Filters/ToJPEG`, 파일 등록 | [Sample.py](Sample.py) | `/thumbs/sample`, `/favicon.ico`, `/css/sample.css`, `/` |
| `Model.py` | [Requests.py](Requests.py) | 기존 JSON 결과 구조를 딕셔너리로 생성; 추가 스키마는 Content·ResponseSpecification으로 선언 |
| `SampleHandler` 출력 | [Sample.py](Sample.py) | 표준 로깅과 서버 오류·연결 종료 로깅 사용 |
| `RunGetDocument` | [Sample.py](Sample.py) | Specifications 확장의 GET `/api/doc`에서 OpenAPI 3.1 제공 |
| `scripts/DescriptionToFile` | [DescriptionToFile.py](scripts/DescriptionToFile.py) | 같은 Application의 OpenAPI 문서를 파일로 저장 |

다음 항목은 이번 실행 샘플에 포함하지 않는다.

- ReDoc 뷰어와 WSGI 전용 `DocumentHandler`: 이전하지 않았다. API 문서·실행 UI는 같은 Application의 Swagger 확장을 사용한다. OpenAPI JSON은 외부 문서 도구에서도 사용할 수 있다.
- WebSocket: 이전 범위에서 제외했다.

기존 구현의 버그를 복제하지 않은 부분은 다음과 같다.

- 폼 디코딩을 중복 적용하지 않는다. 반복 키는 리스트로 유지한다.
- 쿠키는 인증 샘플이 요구하는 문자열 값을 전달한다.
- JSON 배열 샘플은 리스트만 허용한다. 일반 `IsArray`가 다른 iterable까지 허용하는 것을 JSON 배열 허용으로 해석하지 않는다.
- 스트림 입력은 전체를 모으지 않고 읽은 바이트를 즉시 Chunked 응답으로 쓴다. 일반 스트림 출력은 길이를 고정하는 대신 연결 종료로 구분한다.
- SSE의 연결 종료를 광범위한 예외 처리로 삼키지 않는다. 서버가 기록하고 핸들러를 해제한다.
- 환영 페이지는 아직 없는 문서 UI나 외부 CDN에 의존하지 않도록 조정했다.

## 요청 예시

### 경로·쿼리·JSON

```powershell
curl.exe "http://127.0.0.1:8000/api/run/101/102?a=6&b=10"
curl.exe -X POST -H "Content-Type: application/json" --data-binary '{"a":2,"b":3}' "http://127.0.0.1:8000/api/run/101/102?a=6&b=10"
```

GET은 `data.ret=12432`, POST는 `data.ret=12995`를 반환한다. 경로 값은 100 초과, 쿼리 `a`는 5 초과·`b`는 9 초과가 필요하다. 본문 `a`는 5 미만·`b`는 9 미만이다. PUT·DELETE도 같은 JSON 입력을 받고 각각 기존 곱셈·뺄셈 계산을 수행한다. 기본 메시지는 `안녕`이다.

`/swagger`에서 계산 API를 펼치면 경로·쿼리 입력 제약, 이름 있는 `CalculationInput`·`CalculationResult` 스키마와 JSON 본문 예제를 확인할 수 있다. Try it out에서 경로 `101`·`102`, 쿼리 `6`·`10`, POST 본문 `{"a":2,"b":3}`을 입력하고 Execute를 누르면 `12995` 계산 결과를 확인할 수 있다. Swagger UI의 JS·CSS는 CDN에서 불러오므로 브라우저의 인터넷 연결이 필요하다.

```powershell
curl.exe -X POST -H "Content-Type: application/json" --data-binary '[1,2,3]' http://127.0.0.1:8000/api/content/array
curl.exe -X POST -H "Content-Type: application/octet-stream" -H "Content-Format: application/octet-stream" --data-binary "hello" http://127.0.0.1:8000/api/run/upload
```

첫 응답은 `[1,2,3]`, 두 번째는 `hello`다. 배열 경로에 객체를 보내면 400이다. 본문이 있는데 Content-Type이 없으면 ClientError다.

### 인증

이 샘플의 인증 값과 토큰은 **예제 전용 고정 문자열 `1`**이다. 실제 OAuth2 공급자·사용자 인증 서버로 사용하면 안 된다. 비밀번호·토큰 폼 값의 에코도 원본 시나리오 재현을 위한 것이므로 실제 자격 정보를 보내지 않는다.

```powershell
curl.exe "http://127.0.0.1:8000/api/auth/query?credentials=1"
curl.exe -H "credentials: 1" http://127.0.0.1:8000/api/auth/header
curl.exe -H "Cookie: credentials=1" http://127.0.0.1:8000/api/auth/cookie
curl.exe -H "Authorization: Bearer 1" http://127.0.0.1:8000/api/auth/http
```

성공 시 `extra.id=0`인 세션을 반환하고, 인증 정보가 없거나 값이 잘못되면 401이다.

| 흐름 | 토큰 요청 | 인증 확인 경로 |
| --- | --- | --- |
| implicit | GET `/api/auth/oauth2/implicit/token?response_type=token&client_id=sample` | `/api/auth/oauth2/implicit` |
| password | POST `/api/auth/oauth2/password/token`, 폼 `username=sample&password=example` | `/api/auth/oauth2/password` |
| clientCredentials | POST `/api/auth/oauth2/clientcredentials/token`, 폼 `client_id=sample&client_secret=example` | `/api/auth/oauth2/clientcredentials` |
| authorizationCode | GET `/api/auth/oauth2/authorizationcode/token?response_type=code&client_id=sample` | `/api/auth/oauth2/authorizationcode` |

POST 토큰 요청은 `Content-Type: application/x-www-form-urlencoded`가 필요하다. 토큰 응답의 `access_token`, `refresh_token`은 모두 `1`이다. 인증 확인 경로는 `Authorization: Bearer 1`을 받는다.

### 스트림·SSE

```powershell
curl.exe -N http://127.0.0.1:8000/api/run/stream
curl.exe -N http://127.0.0.1:8000/api/run/stream/chunked
curl.exe -N http://127.0.0.1:8000/api/run/stream/sse
curl.exe -N -X PUT -H "Content-Type: application/octet-stream" --data-binary "hello" http://127.0.0.1:8000/api/run/stream
curl.exe -N -X PUT -H "Content-Type: application/octet-stream" -H "Transfer-Encoding: chunked" --data-binary "hello" http://127.0.0.1:8000/api/run/stream/chunked
```

GET 스트림은 1초 간격으로 `0`부터 `9`까지 출력하고 종료한다. PUT은 `hello`를 반환한다. SSE는 무한히 임의 숫자와 ID를 보내고 5의 배수일 때 `retry: 1000`을 보낸다. 클라이언트를 종료해 연결을 닫는다.

### CORS·OPTIONS·파일

```powershell
curl.exe -i -X OPTIONS -H "Origin: https://client.example" -H "Access-Control-Request-Method: GET" http://127.0.0.1:8000/status
curl.exe -i "http://127.0.0.1:8000/options?p=/status"
curl.exe -o sample.jpg http://127.0.0.1:8000/thumbs/sample
```

첫 요청은 204와 허용 Origin·메서드를 반환한다. 두 번째 GET 요청은 200과 Allow 헤더 및 해당 경로의 OpenAPI 본문을 반환한다. `/options`에 `method`를 지정한 preflight 조회는 204를 유지한다. 마지막 요청은 로컬 이미지 파일을 내려받는다. 샘플 상태 경로는 CORS 예시를 위해 모든 Origin을 허용하며, 다른 경로에는 임의의 CORS 허용을 추가하지 않는다.

## Application 확장과 문서

샘플 생성자는 `Application(exts=(...))`로 다음 경로를 연결한다. 별도 Inspector 포트는 없다.

| 경로 | 기능 |
| --- | --- |
| `/metrics` | HTTP 요청·전송 완료 Metrics |
| `/status` | Status: 실시간 지표 UI; `/metrics`의 JSON 스냅샷 조회 |
| `/api/doc` | OpenAPI 3.1 JSON |
| `/swagger` | CDN 기반 Swagger UI·요청/응답 명세·Try it out |
| `/health` | Ping: 실행 상태 확인 |

```powershell
python -m samples.scripts.DescriptionToFile .\openapi.json
```

서버를 띄우지 않고 동일한 라우트 선언의 문서를 생성한다. 입력·응답 스키마를 생략한 샘플에는 가짜 제약이나 응답 스키마를 채우지 않는다. 샘플은 로컬 개발용으로 진단 경로에 인증을 설정하지 않았으며 실제 비밀 정보를 입력하거나 공개 인터넷에 노출하지 않는다.

## 검증

```powershell
python -m unittest discover -s .\tests -p "test_samples.py" -v
```

임시 포트의 실제 HTTP 서버에서 일반 요청·검증·인증·토큰·파일·스트림을 검증한다. SSE 샘플의 이벤트·ID·retry와 종료 전파는 가짜 시간 경계에서 확인하고, 실제 소켓 SSE 동시성·연결 종료는 핵심 Writer 테스트가 검증한다.
