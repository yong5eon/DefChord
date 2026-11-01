from http.server import (
	BaseHTTPRequestHandler,
	ThreadingHTTPServer,
)
from logging import getLogger
from typing import (
	Optional,
	Union,
)

from ....Application import Application
from ....Error import Error
from ....Request import Request
from ....IO.RequestReader import RequestReader
from ....Response import Response
from ....IO.ResponseWriter import ResponseWriter
from ....Startup import startup
from ...Server import Server as ServerAdapter
from ...RequestHandler import handle_request

__all__ = (
	'Server',
	'ServerRequestHandler',
)


class Server(
	ThreadingHTTPServer,
	ServerAdapter,
):
	"""Run the built-in HTTP transport without external dependencies."""

	daemon_threads = True
	app: Application
	logger = getLogger('DefChord.Server')

	def __init__(
		self,
		host: str,
		port: int,
		application: Application,
		*,
		poll_interval: float = 0.5,
	):
		ServerAdapter.__init__(
			self,
			host,
			port,
			application,
		)
		self.app = application
		self.poll_interval = poll_interval
		try:
			ThreadingHTTPServer.__init__(
				self,
				(
					host,
					port,
				),
				ServerRequestHandler,
			)
		except Exception:
			self.logger.exception('Server bind failed: adapter=Python host=%s port=%s', host, port)
			raise
		return

	def run(self) -> None:
		"""Close the listening socket and ensure extensions shut down when serving stops."""
		with self:
			self.serve_forever(self.poll_interval)
		self.logger.info('Server stopped: adapter=Python')
		return

	def serve_forever(
		self,
		poll_interval: float = 0.5,
	) -> None:
		host = self.server_address[0]
		if not isinstance(host, str):
			raise TypeError('HTTP listen address must be a string')
		self.logger.info('Server starting: adapter=Python host=%s port=%s', host, self.server_port)
		startup(
			self.application,
			'Python',
			host,
			self.server_port,
		)
		self.app.start()
		self.logger.info('Server ready: adapter=Python host=%s port=%s', host, self.server_port)
		try:
			super().serve_forever(poll_interval=poll_interval)
		except KeyboardInterrupt:
			self.logger.info('Shutdown requested by keyboard interrupt: adapter=Python')
		except Exception:
			self.logger.exception('Server execution failed: adapter=Python')
			raise
		finally:
			self.logger.info('Server stopping: adapter=Python')
			self.app.stop()
		self.logger.info('Server serving stopped: adapter=Python')
		return


class ServerRequestHandler(BaseHTTPRequestHandler):
	server: Server
	protocol_version = 'HTTP/1.1'
	server_version = 'DefChord'
	logger = getLogger('DefChord.Server')

	def request_reader(self) -> RequestReader:
		lengths = self.headers.get_all('Content-Length', [])
		transfers = self.headers.get_all('Transfer-Encoding', [])
		if len(self.headers.get_all('Content-Type', [])) > 1:
			raise Error(
				400,
				'Duplicate Content-Type',
			)
		if len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers):
			raise Error(
				400,
				'Ambiguous request body framing',
			)
		size: Optional[int] = None
		if lengths:
			if not lengths[0].isascii() or not lengths[0].isdigit():
				raise Error(
					400,
					'Invalid Content-Length',
				)
			size = int(lengths[0])
		if transfers and transfers[0].lower() != 'chunked':
			raise Error(
				400,
				'Unsupported Transfer-Encoding',
			)
		return RequestReader(
			self.rfile,
			size=size,
			chunked=bool(transfers),
		)

	def handle_one_request(self) -> None:
		self.close_connection = True
		try:
			self.raw_requestline = self.rfile.readline(65537)
			if len(self.raw_requestline) > 65536:
				self.requestline = ''
				self.request_version = ''
				self.command = ''
				self.send_error(414)
				return
			if not self.raw_requestline:
				return
			if not self.parse_request():
				return
		except ConnectionError:
			self.logger.warning('Client disconnected before request parsing: adapter=Python')
			return
		self.close_connection = True
		writer = ResponseWriter(
			self.begin_response,
			self.wfile,
			method=self.command,
			version=self.request_version,
		)

		def create_request() -> Request:
			return Request(
				address=self.client_address[0],
				port=self.client_address[1],
				method=self.command,
				uri=self.path,
				headers=dict(self.headers.items()),
				reader=self.request_reader(),
				writer=writer,
			)

		try:
			handle_request(
				self.server.app,
				create_request,
				writer,
			)
		except Exception:
			# The shared handler logs transport errors; finish by closing the connection.
			self.close_connection = True
		return

	def begin_response(
		self,
		response: Response,
		chunked: bool,
	) -> None:
		length = response.header('Content-Length')
		self.response_status = response.status
		self.send_response(
			response.status,
			response.message,
		)
		no_body = (
			self.command == 'HEAD'
			or response.status in (
				204,
				205,
				304,
			)
			or response.status < 200
		)
		upgrade = response.status == 101
		excluded = (
			'content-length',
			'transfer-encoding',
		) if upgrade else (
			'connection',
			'content-length',
			'transfer-encoding',
		)
		for key, value in response.headers():
			if key.lower() not in excluded:
				self.send_header(
					key,
					value,
				)
		if chunked and not no_body:
			self.send_header(
				'Transfer-Encoding',
				'chunked',
			)
		elif length is not None and response.status not in (
			204,
			205,
			304,
		):
			self.send_header(
				'Content-Length',
				length,
			)
		if response.status == 205:
			self.send_header(
				'Content-Length',
				'0',
			)
		if not upgrade:
			self.send_header(
				'Connection',
				'close',
			)
		self.end_headers()
		return

	def log_message(
		self,
		format: str,
		*args: object,
	) -> None:
		self.logger.debug(
			'HTTP parser diagnostic: method=%s',
			ascii(self.command[:32]) if self.command is not None else None,
		)
		return

	def log_request(
		self,
		code: Union[int, str] = '-',
		size: Union[int, str] = '-',
	) -> None:
		"""Keep shared result logging separate because selecting headers does not complete transmission."""
		self.logger.debug(
			'HTTP response headers selected: status=%s method=%s',
			code,
			ascii(self.command[:32]) if self.command is not None else None,
		)
		return
