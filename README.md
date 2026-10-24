# DefEssential

동기식 Python 웹 애플리케이션 프레임워크

**Just def.**<br>
**Let web apps do the work.**<br>
**You don't need to await this.**

[English](./README.en.md)

DefEssential은 일반 Python 메서드로 HTTP 요청을 처리하는 동기식 웹 프레임워크입니다.
`async` / `await` 없이 라우트, 요청 검증, 응답, 확장 기능을 구성할 수 있습니다.

- **동기식 요청 처리**: `RequestRunner` 클래스로 HTTP 메서드와 경로, 핸들러를 선언합니다.
- **요청 검증**: 경로·쿼리·헤더·본문 값에 검증기와 변환기를 적용합니다.
- **응답과 스트리밍**: JSON·텍스트·파일 응답, 스트리밍, Server-Sent Events, WebSocket을 지원합니다.
- **확장 기능**: 상태 확인, Ping, Metrics, OpenAPI 명세와 Swagger UI, 파일 제공 기능을 조합할 수 있습니다.
- **서버 어댑터**: 기본 Python 서버를 제공하며 Gunicorn과 Uvicorn 어댑터를 선택적으로 설치할 수 있습니다.
- **생명주기 훅**: 애플리케이션, 확장, 요청 실행 단계에 훅을 등록할 수 있습니다.

## 요구 사항 및 설치

- Python 3.9 이상

```bash
pip install DefEssential
```

기본 Python 서버는 추가 서버 의존성 없이 사용할 수 있습니다. 선택적 어댑터가 필요한 경우 해당 추가 기능을 설치합니다.

```bash
pip install "DefEssential[Gunicorn]"
pip install "DefEssential[Uvicorn]"
```

## 빠른 시작

```python
from DefEssential import Application, Request, RequestRunner
from DefEssential.Adapter.Implements.Python import Server
from DefEssential.Responses import ResponseText


class Hello(RequestRunner, method='GET', url='/hello'):
  def run(self, request: Request):
    return ResponseText('Hello, world!')


application = Application()
application.add(Hello)

Server('127.0.0.1', 8000, application).run()
```

서버를 실행한 뒤 `GET /hello` 요청은 `Hello, world!`를 반환합니다. 각 요청은 새로운 핸들러 인스턴스에서 처리됩니다.

## 요청 핸들러와 검증

`RequestRunner` 하위 클래스 선언에서 `method`와 `url`을 지정하고 `run()` 메서드에 동기식 처리 로직을 작성합니다. URL 경로 변수는 `:name` 형식으로 선언하며, `parameters`, `qs`, `headers`, `body` 설정에 검증 규칙을 지정할 수 있습니다.

```python
from DefEssential import (
  Parameters,
  Request,
  RequestRunner,
)
from DefEssential.Responses import ResponseJSON
from DefEssential.Validator.Patterns import (
  IsGreaterThan,
  ToInteger,
)


class ReadValue(
  RequestRunner,
  method='GET',
  url='/values/:value',
  parameters=Parameters({
    'value': ToInteger(IsGreaterThan(0)),
  }),
):
  def run(self, request: Request):
    return ResponseJSON({'value': request.parameters['value']})
```

검증기와 변환기는 요청 입력을 핸들러에 전달하기 전에 실행됩니다. 본문은 `Body`와 콘텐츠 리더를 통해 JSON, 텍스트, 바이너리 또는 스트리밍 방식으로 읽을 수 있습니다.

## 응답, 스트리밍 및 프로토콜

- `ResponseJSON`, `ResponseText`, `ResponseFile`로 JSON, 텍스트, 파일 응답을 만들 수 있습니다.
- `request.writer`와 스트림 writer로 응답 본문을 직접 스트리밍할 수 있습니다. 이 방식에서는 핸들러가 응답을 직접 기록하고 `None`을 반환합니다.
- Server-Sent Events writer로 이벤트 스트림을 전송할 수 있습니다.
- `WebSocket` API는 HTTP 연결을 업그레이드한 뒤 text 및 binary 메시지를 송수신합니다.

직접 출력 및 스트리밍 응답은 일반 반환 응답과 처리 시점이 다릅니다. 관련 훅 계약과 전송 동작에 맞춰 응답 처리를 구성하세요.

## 확장 기능과 서버

확장 기능은 `Application(exts=...)`에 전달해 사용합니다. 기본 제공 확장은 다음과 같습니다.

- `Status`: 상태 페이지 제공
- `Ping`: 애플리케이션 실행 상태 응답
- `Metrics`: JSON 또는 Prometheus 형식의 요청 통계 제공
- `Specifications`: 등록된 라우트로부터 OpenAPI 3.1 문서 생성
- `Swagger`: Swagger UI 제공
- `File`, `FileSystem`: 고정 파일 또는 파일 시스템 콘텐츠 제공

기본 서버는 `DefEssential.Adapter.Implements.Python.Server`입니다. Gunicorn과 Uvicorn 어댑터는 각각 `DefEssential[Gunicorn]`, `DefEssential[Uvicorn]` 추가 기능으로 설치합니다. 어댑터와 worker 방식에 따라 지원 환경과 전송 특성이 다를 수 있습니다.

## 생명주기 훅과 로깅

`Application`은 `on_startup`, `on_cleanup`, `on_request`, `on_request_response`, `on_request_error` 훅을 받을 수 있습니다. `Extension`은 시작·정리·요청·응답·오류 훅을, `RequestRunner`는 요청·응답·오류 훅을 지원합니다.

DefEssential은 표준 `logging` 로거를 사용하며 애플리케이션의 핸들러나 로그 레벨을 대신 설정하지 않습니다. 애플리케이션에서 필요한 로거와 출력 정책을 구성하세요.

## 샘플 및 테스트

저장소의 `samples/Sample.py`에는 요청, 검증, 인증, 파일, 스트리밍, WebSocket 및 기본 제공 확장을 포함한 실행 예제가 있습니다. 프로젝트 루트에서 다음 명령으로 샘플 서버를 실행할 수 있습니다.

```bash
python samples/Sample.py
```

저장소 코드를 테스트하려면 프로젝트 루트에서 editable 설치를 한 뒤 다음 명령을 실행합니다.

```bash
pip install -e .
python -m unittest discover -s tests
```

## 라이선스

라이선스 조건은 저장소의 `LICENSE` 파일을 확인하세요.
