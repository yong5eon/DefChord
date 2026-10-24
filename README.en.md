# DefEssential

The modern synchronous Python web application framework

**Just def.**<br>
**Let web apps do the work.**<br>
**You don't need to await this.**

[한국어](./README.md)

DefEssential is a synchronous web framework for handling HTTP requests with ordinary Python methods.
Configure routes, request validation, responses, and extensions without `async` / `await`.

- **Synchronous request handling**: Declare HTTP methods, paths, and handlers with `RequestRunner` classes.
- **Request validation**: Apply validators and converters to path, query, header, and body values.
- **Responses and streaming**: Support JSON, text, and file responses, streaming, Server-Sent Events, and WebSocket.
- **Extensions**: Combine health status, Ping, Metrics, OpenAPI specifications, Swagger UI, and file-serving features.
- **Server adapters**: Use the built-in Python server or optionally install the Gunicorn and Uvicorn adapters.
- **Lifecycle hooks**: Register hooks for application, extension, and request execution lifecycles.

## Requirements and installation

- Python 3.9 or later

```bash
pip install DefEssential
```

The built-in Python server requires no additional server dependency. Install an optional extra to use another adapter.

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

After starting the server, a `GET /hello` request returns `Hello, world!`. Each request is handled by a new handler instance.

## Request handlers and validation

Declare `method` and `url` on a `RequestRunner` subclass and implement synchronous request handling in `run()`. Declare URL path parameters with the `:name` syntax and configure validation rules with `parameters`, `qs`, `headers`, and `body`.

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

Validators and converters run before input is passed to the handler. Read request bodies as JSON, text, binary data, or streams through `Body` and content readers.

## Responses, streaming, and protocols

- Create JSON, text, and file responses with `ResponseJSON`, `ResponseText`, and `ResponseFile`.
- Stream response bodies through `request.writer` and stream writers. In this mode, the handler writes the response directly and returns `None`.
- Send event streams with the Server-Sent Events writer.
- Use the `WebSocket` API to exchange text and binary messages after upgrading an HTTP connection.

Direct-output and streaming responses have different processing timing from ordinary returned responses. Configure response handling according to the relevant hook contracts and transport behavior.

## Extensions and servers

Pass extensions to `Application(exts=...)`. Built-in extensions include:

- `Status`: provide a status page
- `Ping`: report the application's running state
- `Metrics`: expose request metrics as JSON or Prometheus
- `Specifications`: generate an OpenAPI 3.1 document from registered routes
- `Swagger`: provide Swagger UI
- `File`, `FileSystem`: serve fixed files or file-system content

The built-in server is `DefEssential.Adapter.Implements.Python.Server`. Install the `DefEssential[Gunicorn]` or `DefEssential[Uvicorn]` extra for the corresponding adapter. Supported environments and transport characteristics vary by adapter and worker type.

## Lifecycle hooks and logging

`Application` accepts `on_startup`, `on_cleanup`, `on_request`, `on_request_response`, and `on_request_error` hooks. `Extension` supports startup, cleanup, request, response, and error hooks; `RequestRunner` supports request, response, and error hooks.

DefEssential uses standard `logging` loggers and does not configure application handlers or log levels. Configure the loggers and output policy required by your application.

## Samples and tests

`samples/Sample.py` in the repository demonstrates requests, validation, authentication, files, streaming, WebSocket, and built-in extensions. Run the sample server from the project root:

```bash
python samples/Sample.py
```

Install the current checkout in editable mode from the project root, then run the tests:

```bash
pip install -e .
python -m unittest discover -s tests
```

## License

See the `LICENSE` file in the repository for license terms.
