# DefEssential

The Modern Synchronous Python Web Application Framework

**Just def.**<br>
**Let web apps do the work.**<br>
**You don't need to await this.**

[한국어](./README.md)

DefEssential is a synchronous web framework for handling HTTP requests with ordinary Python methods. Configure routes, request validation, responses, and extensions without `async` / `await`.

- Validation for path, query, header, and body inputs
- JSON, text, and file responses; streaming, Server-Sent Events, and WebSocket
- Extensions for status checks, metrics, OpenAPI, Swagger UI, and file serving
- Built-in Python server with optional Gunicorn and Uvicorn adapters

## Requirements and installation

Requires Python 3.9 or later. The built-in server is available without extra server dependencies.

```shell
python -m pip install DefEssential
```

Install an extra only when using the corresponding Gunicorn or Uvicorn adapter.
The core contains neither adapter's code. Each extra installs a separate, same-version implementation distribution and its dependencies.

```shell
python -m pip install "DefEssential[Gunicorn]"
python -m pip install "DefEssential[Uvicorn]"
```

See [installation isolation, development and distribution](./docs/Packaging.en.md) for migration from the integrated distribution and editable development.

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

After starting the server, send a `GET /hello` request to receive `Hello, world!`. See the [detailed guide](./docs/README.en.md) for request validation, streaming responses, lifecycle hooks, and server configuration.

## Documentation and releases

- [Detailed guide (English)](./docs/README.en.md)
- [Releases and change history](https://github.com/yong5eon/DefEssential/releases)

See the repository's `LICENSE` file for license terms.
