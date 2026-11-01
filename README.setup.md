# DefChord

The Modern Synchronous Python Web Application Framework

DefChord is a synchronous Python web framework for handling HTTP requests with ordinary methods. Python 3.9 or later is required.

## Installation

```shell
python -m pip install DefChord
```

The built-in Python HTTP server requires no additional server dependency. Optional extras provide Gunicorn and Uvicorn adapters:
The core excludes their implementation files; each extra installs a separate, same-version adapter distribution and its dependencies.

```shell
python -m pip install "DefChord[Gunicorn]"
python -m pip install "DefChord[Uvicorn]"
```

Install the desired adapter extra when needed. Omitting an extra later does not remove an already installed adapter.

## Quick start

Save this example as `app.py` and run `python app.py`.

```python
from DefChord import Application, Request, RequestRunner
from DefChord.Adapter.Implements.Python import Server
from DefChord.Responses import ResponseText


class Hello(RequestRunner, method='GET', url='/hello'):
  def run(self, request: Request):
    return ResponseText('Hello, world!')


application = Application()
application.add(Hello)
Server('127.0.0.1', 8000, application).run()
```

The server listens on `127.0.0.1:8000`. A `GET /hello` request returns `Hello, world!`.

## License

See the `LICENSE` file included with the source distribution for license terms.
