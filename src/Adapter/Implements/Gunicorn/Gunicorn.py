from atexit import register
from io import BytesIO
from queue import Queue
from threading import Thread
from typing import Optional

from ...Adapter import Adapter
from ....Request import Request
from ....RequestReader import RequestReader
from ....Response import Response
from ....ResponseWriter import ResponseWriter


class _Output:
	def __init__(self, events):
		self.events = events
		self.status: Optional[int] = None
		return

	def write(self, data: bytes) -> int:
		self.events.put(('body', data))
		return len(data)

	def flush(self) -> None:
		return


class GunicornAdapter(Adapter):
	"""Expose a DefEssential Application as a WSGI callable for Gunicorn."""

	def __init__(self, app):
		super().__init__(app)
		self.started = False
		self._start_lock = __import__('threading').Lock()
		register(self.stop)
		return

	def start(self) -> None:
		with self._start_lock:
			if not self.started:
				self.app.start()
				self.started = True
		return

	def stop(self) -> None:
		with self._start_lock:
			if self.started:
				self.started = False
				self.app.stop()
		return

	def __call__(
		self,
		environ,
		start_response,
	):
		self.start()
		headers = {}
		for key, value in environ.items():
			if key.startswith('HTTP_'):
				headers[key[5:].replace('_', '-')] = value
		if environ.get('CONTENT_TYPE'):
			headers['Content-Type'] = environ['CONTENT_TYPE']
		length = environ.get('CONTENT_LENGTH', '')
		if length:
			headers['Content-Length'] = length
		reader = RequestReader(
			environ.get('wsgi.input', BytesIO()),
			size=int(length) if length else 0,
		)
		events = Queue()
		output = _Output(events)

		def send(response: Response, chunked: bool) -> None:
			output.status = response.status
			response_headers = response.headers()
			if chunked:
				response_headers = [
					(key, value) for key, value in response_headers
					if key.lower() != 'transfer-encoding'
				]
			events.put(('start', response.status, response.message, response_headers))
			return

		writer = ResponseWriter(
			send,
			output,
			method=environ.get('REQUEST_METHOD', 'GET'),
			version=environ.get('SERVER_PROTOCOL', 'HTTP/1.1'),
		)
		request = Request(
			address=environ.get('REMOTE_ADDR', ''),
			port=int(environ.get('REMOTE_PORT') or 0),
			method=environ.get('REQUEST_METHOD', 'GET'),
			uri=environ.get('RAW_URI') or environ.get('REQUEST_URI') or environ.get('PATH_INFO', '/') + (
				'?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else ''
			),
			headers=headers,
			reader=reader,
			writer=writer,
		)

		def run() -> None:
			try:
				self.dispatch(request)
			finally:
				events.put(('end',))

		Thread(target=run, daemon=True).start()

		def body():
			started = False
			while True:
				event = events.get()
				if event[0] == 'start':
					_, status, message, response_headers = event
					start_response(f'{status} {message}', response_headers)
					started = True
				elif event[0] == 'body':
					if started:
						yield event[1]
				else:
					break
			return

		return body()
