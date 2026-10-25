# DefEssential

The Modern Synchronous Python Web Application Framework

**Just def.**<br>
**Let web apps do the work.**<br>
**You don't need to await this.**

## Requirements

- Python 3.9 or later

## Installation

```bash
pip install DefEssential
```

The package includes a built-in Python HTTP server. Optional extras provide additional server adapters:

```bash
pip install "DefEssential[Gunicorn]"
pip install "DefEssential[Uvicorn]"
```

## Quick start

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

The handler declares an HTTP method and path on its `RequestRunner` class. The application registers the handler, and the server runs the application. A `GET /hello` request returns a plain-text response.

## Request handling

Define handlers as `RequestRunner` subclasses and implement `run()` with synchronous Python code. Configure path, query, header, and body validation in the class declaration. The framework also provides JSON, text, and file responses, direct streaming, Server-Sent Events, WebSocket support, and extensions for status checks, metrics, OpenAPI specifications, Swagger UI, and file serving.

## License

See the `LICENSE` file included with the source distribution for license terms.
