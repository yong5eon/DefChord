from typing import (
	Any,
	Mapping,
)

from ....IO.Readers.ChunkedStream import ChunkedStream
from ....IO.RequestReader import RequestReader
from ....IO.ResponseWriter import ResponseWriter
from ....Response import Response
from ...WSGI import (
	StartResponse,
	WSGIApplication,
	WSGIResponseWriter,
	WSGITransport,
)

__all__ = (
	'Input',
	'Body',
	'Transport',
	'Writer',
	'GunicornApplication',
)


class Input:
	"""Share the Gunicorn parser's buffered input and body state with the framework and worker."""

	def __init__(
		self,
		request: Any,
	):
		self.unreader = request.unreader
		headers = dict(request.headers)
		length = headers.get('CONTENT-LENGTH')
		self.request_reader = RequestReader(
			self,
			size=int(length) if length is not None else None,
			chunked=headers.get('TRANSFER-ENCODING', '').lower() == 'chunked',
		)
		self.body = ChunkedStream(self.request_reader) if self.request_reader.chunked else self.request_reader
		return

	def read(
		self,
		size: int = -1,
		/,
	) -> bytes:
		return self.unreader.read(size)

	def readline(
		self,
		size: int = -1,
		/,
	) -> bytes:
		parts = []
		while size < 0 or len(parts) < size:
			data = self.unreader.read(1)
			if not data:
				break
			parts.append(data)
			if data == b'\n':
				break
		return b''.join(parts)


class Body:
	"""Preserve the application's read position when the worker discards the remaining body."""

	def __init__(
		self,
		request: Any,
	):
		self.input = Input(request)
		return

	def read(
		self,
		size: int = -1,
	) -> bytes:
		return self.input.body.read(size)

	def readline(
		self,
		size: int = -1,
	) -> bytes:
		return self.input.body.readline(size)


class Transport(WSGITransport):
	"""Delegate HTTP to Gunicorn and use the raw socket after a 101 upgrade."""

	def __init__(
		self,
		start_response: StartResponse,
		socket: Any,
	):
		super().__init__(start_response)
		self.socket = socket
		self.upgraded = False
		return

	def begin(
		self,
		response: Response,
		chunked: bool,
	) -> None:
		if response.status != 101:
			super().begin(
				response,
				chunked,
			)
			return
		output = self.start_response(
			f'{response.status} {response.message}',
			response.headers(),
		)
		output(b'')
		self.upgraded = True
		return

	def write(
		self,
		data: bytes,
		/,
	) -> int:
		if self.upgraded:
			self.socket.sendall(data)
			return len(data)
		return super().write(data)


class Writer(WSGIResponseWriter):
	def upgrade(
		self,
		response: Response,
	) -> None:
		ResponseWriter.upgrade(
			self,
			response,
		)
		return


class GunicornApplication(WSGIApplication):
	"""Provide the same I/O and WebSocket API for sync, gthread, and gevent workers."""

	def request_reader(
		self,
		environ: Mapping[str, Any],
	) -> RequestReader:
		body = environ['wsgi.input']
		if not isinstance(body, Body):
			raise TypeError('Gunicorn input hook was not installed')
		return body.input.request_reader

	def response_writer(
		self,
		environ: Mapping[str, Any],
		start_response: StartResponse,
	) -> ResponseWriter:
		transport = Transport(
			start_response,
			environ['gunicorn.socket'],
		)
		return Writer(
			transport.begin,
			transport,
			method=environ['REQUEST_METHOD'],
			version=environ['SERVER_PROTOCOL'],
		)
