from typing import (
	Any,
	Callable,
	Iterable,
	Mapping,
	Optional,
	Protocol,
)
from urllib.parse import quote_from_bytes
from wsgiref.util import is_hop_by_hop

from ..Application import Application
from ..Error import Error
from ..IO.RequestReader import RequestReader
from ..IO.ResponseWriter import ResponseWriter
from ..Request import Request
from ..Response import Response
from .RequestHandler import handle_request


class StartResponse(Protocol):
	def __call__(
		self,
		status: str,
		headers: list[tuple[str, str]],
		/,
	) -> Callable[[bytes], object]:
		...


class WSGITransport:
	"""HTTP 프레이밍을 WSGI 서버에 맡기고 바이트를 즉시 전달한다."""

	def __init__(
		self,
		start_response: StartResponse,
	):
		self.start_response = start_response
		self.output: Optional[Callable[[bytes], object]] = None
		return

	def begin(
		self,
		response: Response,
		chunked: bool,
	) -> None:
		headers = [
			(
				key,
				value,
			) for key, value in response.headers()
			if not is_hop_by_hop(key)
			and not (key.lower() == 'content-length' and response.status in (
				204,
				205,
				304,
			))
		]
		if response.status == 205:
			headers.append((
				'Content-Length',
				'0',
			))
		self.output = self.start_response(
			f'{response.status} {response.message}',
			headers,
		)
		return

	def write(
		self,
		data: bytes,
		/,
	) -> int:
		if self.output is None:
			raise RuntimeError('WSGI response must be started before writing')
		self.output(data)
		return len(data)

	def flush(self) -> None:
		# WSGI의 write() 호출 자체가 서버로 바이트를 전달한다.
		return


class WSGIResponseWriter(ResponseWriter):
	"""직접 출력 API를 유지하면서 청크 프레이밍의 중복 적용을 방지한다."""

	def start(
		self,
		response: Response,
		chunked: bool,
	) -> None:
		super().start(
			response,
			False,
		)
		return

	def upgrade(
		self,
		response: Response,
	) -> None:
		raise Error(
			501,
			'WSGI adapters do not support protocol upgrades',
		)


class WSGIApplication:
	"""DefEssential 요청을 Gunicorn과 a2wsgi의 WSGI 호출에 연결한다."""

	def __init__(
		self,
		application: Application,
	):
		self.application = application
		return

	def request_reader(
		self,
		environ: Mapping[str, Any],
	) -> RequestReader:
		length = environ.get('CONTENT_LENGTH', '')
		transfer = environ.get('HTTP_TRANSFER_ENCODING', '')
		if length and (not length.isascii() or not length.isdigit()):
			raise Error(
				400,
				'Invalid Content-Length',
			)
		if transfer and (transfer.lower() != 'chunked' or length):
			raise Error(
				400,
				'Ambiguous or unsupported request body framing',
			)
		return RequestReader(
			environ['wsgi.input'],
			size=int(length) if length else None,
			chunked=transfer.lower() == 'chunked',
			decoded=True,
		)

	def response_writer(
		self,
		environ: Mapping[str, Any],
		start_response: StartResponse,
	) -> ResponseWriter:
		transport = WSGITransport(start_response)
		return WSGIResponseWriter(
			transport.begin,
			transport,
			method=environ['REQUEST_METHOD'],
			version=environ['SERVER_PROTOCOL'],
		)

	def __call__(
		self,
		environ: Mapping[str, Any],
		start_response: StartResponse,
	) -> Iterable[bytes]:
		writer = self.response_writer(
			environ,
			start_response,
		)

		def create_request() -> Request:
			reader = self.request_reader(environ)
			headers = {
				key[5:].replace('_', '-'): value
				for key, value in environ.items()
				if key.startswith('HTTP_')
			}
			for source, target in (
				(
					'CONTENT_LENGTH',
					'Content-Length',
				),
				(
					'CONTENT_TYPE',
					'Content-Type',
				),
			):
				if environ.get(source):
					headers[target] = environ[source]
			uri = environ.get('RAW_URI') or environ.get('REQUEST_URI')
			if uri is None:
				raw_path = environ.get('asgi.scope', {}).get('raw_path')
				if raw_path is not None:
					uri = raw_path.decode('latin-1')
				else:
					path = environ.get('SCRIPT_NAME', '') + environ['PATH_INFO']
					uri = quote_from_bytes(
						path.encode('latin-1'),
						safe="/:@!$&'()*+,;=-._~",
					)
				if environ.get('QUERY_STRING'):
					uri += '?' + environ['QUERY_STRING']
			return Request(
				address=environ.get('REMOTE_ADDR', ''),
				port=int(environ.get('REMOTE_PORT', 0)),
				method=environ['REQUEST_METHOD'],
				uri=uri,
				headers=headers,
				reader=reader,
				writer=writer,
			)

		handle_request(
			self.application,
			create_request,
			writer,
		)
		return ()
