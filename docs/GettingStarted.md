# 설치와 첫 애플리케이션

[← 매뉴얼 목차](./README.md)

[English](./GettingStarted.en.md)

DefEssential은 동기식 Python 웹 프레임워크입니다. HTTP 서버가 받은 요청을 `Application`으로 전달하고, 등록된 `RequestRunner`가 검증과 애플리케이션 로직을 실행해 `Response`를 반환합니다.

## 설치

Python 3.9 이상이 필요합니다. 기본 설치는 Python 표준 라이브러리 기반 서버를 포함하며, Gunicorn과 Uvicorn adapter는 선택 사항입니다.

```shell
python -m pip install DefEssential
```

다른 서버 adapter를 선택할 때만 해당 extra를 설치합니다.

```shell
python -m pip install "DefEssential[Gunicorn]"
python -m pip install "DefEssential[Uvicorn]"
```

선택하지 않은 어댑터 코드는 설치하지 않습니다. 기존 환경 전환과 editable 개발은 [설치 격리와 개발·배포](./Packaging.md)를 참고하세요.

## 가장 작은 애플리케이션

다음 코드를 `app.py`로 저장합니다.

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

프로젝트 환경에서 서버를 실행합니다.

```shell
python app.py
```

다른 터미널에서 요청을 보내 결과를 확인합니다.

```shell
curl http://127.0.0.1:8000/hello
```

응답 본문은 `Hello, world!`입니다. 서버를 중단하면 요청 처리가 종료됩니다.

## 네 가지 핵심 요소

| 요소 | 책임 |
| --- | --- |
| `Server` | 연결을 수신하고 HTTP 요청·응답을 adapter별 방식으로 처리 |
| `Application` | 라우트를 등록하고 요청을 일치하는 handler에 전달 |
| `RequestRunner` | 경로와 검증 규칙을 선언하고 요청 하나를 처리 |
| `Request` / `Response` | 요청 데이터와 응답 데이터를 서버 환경과 분리해 표현 |

```mermaid
flowchart LR
  C[클라이언트] --> S[Server adapter]
  S --> A[Application]
  A --> R[라우트 탐색]
  R --> H[RequestRunner]
  H --> V[검증과 애플리케이션 로직]
  V --> O[Response 또는 직접 출력]
  O --> S
  S --> C
```

구체적인 라우트·요청 검증과 일반 응답 흐름은 [라우트와 요청, 응답](./RoutingAndRequests.md)에서, 스트리밍 입력·출력과 SSE·WebSocket은 [스트리밍 처리와 WebSocket](./StreamingAndWebSockets.md)에서 이어서 설명합니다.

## 애플리케이션에 라우트 추가

하나의 handler 클래스는 HTTP 메서드와 경로 조합을 선언합니다. 인스턴스는 요청을 처리할 때 생성되므로, handler 인스턴스 필드에 요청 간 상태를 보관하지 마세요.

```python
from DefEssential import Application, Request, RequestRunner
from DefEssential.Responses import ResponseJSON


class Health(RequestRunner, method='GET', url='/health'):
  def run(self, request: Request):
    return ResponseJSON({'status': 'ok'})


application = Application()
application.add(Health)
```

`Application.add()`는 구체 `RequestRunner` 클래스를 받습니다. 서버가 실행 중인 동안에는 handler 등록을 변경할 수 없습니다. 여러 handler를 모듈에서 로드하거나 확장을 등록하는 방법은 [확장과 서버](./ExtensionsAndServers.md)를 참고하세요.

## 다음 단계

1. 경로 매개변수와 메서드 라우팅은 [라우트와 요청, 응답](./RoutingAndRequests.md)에서 학습합니다.
2. 쿼리·헤더·본문 검증 및 콘텐츠 리더는 같은 문서의 요청 검증 절에서 확인합니다.
3. JSON과 파일을 포함한 일반 응답은 [라우트와 요청, 응답](./RoutingAndRequests.md)에서, 스트리밍·SSE·WebSocket은 [스트리밍 처리와 WebSocket](./StreamingAndWebSockets.md)에서 확인합니다.
4. 개발 서버, WSGI 계열 adapter, extensions는 [확장과 서버](./ExtensionsAndServers.md)를 참고합니다.

## 저장소 샘플과 테스트

저장소를 내려받아 개발 중이라면 루트 디렉터리에서 통합 샘플을 실행할 수 있습니다.

```shell
python samples/Sample.py
```

샘플은 여러 route, 요청 validator, 응답, extension, 스트리밍 및 WebSocket 동작을 조합합니다. 기본 Python server가 사용하는 주소와 필요한 샘플 리소스는 실행 결과와 코드에서 확인하세요.

오류 훅이 사용자 정의 응답을 반환하는 예제는 서버 실행 후 `GET http://127.0.0.1:8000/api/run/error`로 확인할 수 있습니다. 이 route는 의도적으로 `418` 오류를 발생시키고 `RequestRunner` 오류 훅에서 `Handled by RequestRunner error hook.` 응답으로 처리합니다.

변경 후 저장소 테스트는 editable 설치 후 실행합니다.

```shell
python -m pip install -e .
python -m unittest discover -s tests
```

위 설치 명령은 코어만 남기므로 선택 어댑터도 개발하려면 `python -m pip install -e . --config-settings EXTRAS=Gunicorn,Uvicorn`을 사용하세요. 기존 파일 수정은 바로 반영되며 새 파일·패키지 구성 변경 후에는 원하는 목록으로 재설치합니다. 전환 절차는 [설치 격리와 개발·배포](./Packaging.md)를 참고하세요. Gunicorn·Uvicorn 전용 테스트나 실행은 서버의 플랫폼 조건을 따릅니다.
