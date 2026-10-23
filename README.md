# DefEssential

The Modern Synchronous Python Web Application Framework

**Just def.**<br>
**Let web apps do the work.**<br>
**You don't need to await this.**

## 공개 API

모든 Python 모듈은 임포트 다음, 구현·정의 이전에 `__all__` 튜플로 공개할 클래스·함수·객체를 명시합니다.
공개할 심볼이 없는 패키지는 `__all__ = ()`를 사용합니다.
외부 라이브러리에서 가져온 구현 의존성과 내부 보조 심볼은 공개 목록에 포함하지 않으며, 기존 패키지의 재노출 API는 유지합니다.
`from ... import *`는 이 목록에 있는 심볼만 가져옵니다. `__all__`은 명시적인 개별 임포트를 차단하지 않습니다.

## 서버 어댑터

서버 인터페이스는 `DefEssential.Adapter.Server`이며, 사용할 구현에서 `Server`를 가져옵니다.
모든 구현은 `Server(host, port, application, ...).run()`으로 실행합니다.

아래 세 호출 형태를 모두 지원합니다. `host`, `port`, `application`은 필수 인수입니다.

```python
server = Server("127.0.0.1", 8000, app)
server.run()
```

```python
Server("127.0.0.1", 8000, app).run()
```

```python
with Server("127.0.0.1", 8000, app) as server:
  server.run()
```

`with` 진입은 같은 서버 인스턴스를 반환하며, 서버 시작은 항상 `run()`에서 수행합니다.
`run()`이 반환하거나 실패하면 실행 자원을 정리하며, `with` 본문에서 발생한 예외도 숨기지 않습니다.
Python 어댑터는 실행하지 않고 `with` 블록을 나가도 생성 시 연 수신 소켓을 닫습니다.
Gunicorn과 Uvicorn은 생성 및 `with` 진입 시 소켓이나 워커를 만들지 않습니다.

각 어댑터는 `startup(application, server, host, port)`를 직접 호출해 시작 정보를 출력합니다.
`Server` 항목에는 `Python`, `Gunicorn`, `Uvicorn`을 표시하며 PID는 출력하지 않습니다.
Gunicorn은 마스터의 `when_ready` 훅에서 시작 배너를 한 번만 출력합니다.
Python은 실제 바인딩 주소를, Gunicorn과 Uvicorn은 설정한 `host`, `port`를 표시합니다.

### Python (기본 서버)

표준 라이브러리만 사용하는 기존 HTTP 서버입니다.

```python
from DefEssential import Application
from DefEssential.Adapter.Implements.Python import Server

app = Application()
# app.add(...) 또는 app.load(...)로 핸들러를 등록합니다.
Server("127.0.0.1", 8000, app).run()
```

`poll_interval`로 종료 확인 주기를 지정할 수 있습니다.
`run()`은 종료 시 애플리케이션과 수신 소켓을 정리합니다.

### Gunicorn

Linux/macOS 등의 POSIX 환경이 필요합니다. Windows에서는 WSL을 사용합니다.

```shell
pip install "DefEssential[Gunicorn]"
```

```python
from DefEssential.Adapter.Implements.Gunicorn import Server

Server(
  "0.0.0.0",
  8000,
  app,
  workers=4,
  worker_class="gthread",
  threads=8,
  timeout=60,
).run()
```

`worker_class`는 WSGI 호환 Gunicorn 워커의 이름, 클래스 경로 또는 워커 클래스입니다.
`workers`의 기본값은 `1`, `worker_class`의 기본값은 `"sync"`입니다.
나머지 키워드 인수는 Gunicorn 설정으로 전달하며, 수신 주소는 `bind` 대신 `host`, `port`로 지정합니다.
애플리케이션과 확장 기능은 마스터가 아닌 각 워커에서 시작하고 종료합니다.
사용자가 지정한 `when_ready`, `pre_request`, `post_worker_init`, `worker_exit` 훅도 유지됩니다.
`pre_request`는 본문을 소비하지 않아야 합니다.

`sync`, `gthread`, `gevent`에서 아래 여섯 기능을 실서버 테스트로 검증합니다.
`gevent`를 선택하면 별도로 `pip install gevent`가 필요합니다.
다른 사용자 정의 워커는 Gunicorn의 HTTP 파서·소켓 계약과 호환되어야 하며, 동일한 검증 범위를 보장하지 않습니다.
`sync`에서는 장시간 SSE/WebSocket 연결 하나가 워커 하나를 점유합니다.
운영 시 동시 연결 수에 맞게 워커 또는 스레드를 확보하고, 장시간 연결에는 Gunicorn의 `timeout`도 조정해야 합니다.

### Uvicorn

HTTP는 `a2wsgi`의 WSGI 환경 변환을 재사용하고, 전용 입출력 연결 계층으로 점진적인 업로드·다운로드를 지원합니다.
WebSocket은 Uvicorn의 프로토콜 확장 지점에서 프레임워크의 기존 핸드셰이크·프레임 처리기를 실행합니다.

```shell
pip install "DefEssential[Uvicorn]"
```

```python
from DefEssential.Adapter.Implements.Uvicorn import Server

Server(
  "0.0.0.0",
  8000,
  app,
  wsgi_workers=10,
  send_queue_size=10,
  log_level="info",
).run()
```

`wsgi_workers`는 HTTP와 WebSocket이 공유하는 동기 요청 처리 스레드 수이며, 프로세스 수가 아닙니다.
장시간 SSE/WebSocket도 처리 중에는 스레드 하나를 점유합니다.
`send_queue_size`는 기존 매개변수 이름을 유지하지만, 현재 전송 계층에서는 수신 본문 이벤트의 버퍼 개수로 사용합니다.
출력은 큐에 쌓지 않고 실제 ASGI 전송 완료까지 기다려 역압을 적용합니다. 두 설정의 기본값은 `10`입니다.
그 외 키워드 인수는 `uvicorn.Config`에 전달합니다.
이미 생성한 `Application` 인스턴스를 받는 API이므로 `workers=1`, `reload=False`, `interface="asgi3"`만 지원합니다.
멀티프로세스 서빙은 Gunicorn 어댑터를 사용합니다.
`ws`, `ws_*` 옵션은 프레임워크의 프레임 처리기와 충돌하므로 명시적으로 거부합니다.
메시지 크기 제한과 ping은 기존 `WebSocket` API로 설정합니다.
WebSocket 압축 확장 및 Uvicorn 자체의 자동 ping은 사용하지 않습니다.

### 전송 기능 지원

| 기능 | Python | Gunicorn (`sync`/`gthread`/`gevent`) | Uvicorn |
| --- | --- | --- | --- |
| Stream In | 지원 | 지원 | 지원 |
| Stream Out | 지원 | 지원 | 지원 |
| Chunked Stream In | 지원 | 지원 | 지원 |
| Chunked Stream Out | 지원 | 지원 | 지원 |
| SSE | 지원 | 지원 | 지원 |
| WebSocket | 지원 | 지원 | 지원 |

같은 동기 핸들러로 모든 조합을 테스트합니다.
입력은 업로드 완료 전에 첫 데이터를 처리하는지, 출력과 SSE는 핸들러 완료 전에 첫 데이터가 도착하는지 확인합니다.
WebSocket은 text·binary·분할 메시지·ping/pong·close를 확인합니다.

### 전송 계층의 차이

- 세 어댑터 모두 요청 처리, 오류 응답, 확장 기능의 요청 관찰과 응답 자원 정리를 공유합니다.
- Gunicorn과 Uvicorn의 HTTP 청크 프레이밍은 서버가 담당합니다. 직접 출력, SSE, iterable 응답에 프레이밍을 중복 적용하지 않습니다.
- Python과 Gunicorn은 원시 HTTP 본문을 읽습니다. Uvicorn은 ASGI가 디코딩한 본문을 점진적으로 읽으므로 원래 클라이언트의 HTTP 청크 경계와 트레일러는 보존하지 않습니다. `chunk(size)`는 이 경우 수신한 데이터 조각을 반환하며, 조각의 크기와 청크 경계에 의존하면 안 됩니다.
- 일반 WSGI 연결 자체는 프로토콜 전환을 지원하지 않습니다. Gunicorn 어댑터는 전용 소켓 연결 계층으로, Uvicorn 어댑터는 네이티브 프로토콜로 WebSocket을 지원합니다. 외부 WSGI 서버에 `WSGIApplication`만 직접 연결하면 전환 요청은 여전히 `501` 오류입니다.
- 선택적 서버 의존성은 해당 어댑터의 `run()`에서만 가져옵니다. 기본 서버와 코어는 외부 의존성 없이 사용할 수 있습니다.
