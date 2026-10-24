from http.server import (
	BaseHTTPRequestHandler,
	ThreadingHTTPServer,
)
from logging import getLogger
from typing import Optional

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
	"""외부 의존성 없이 자체 HTTP 전송 계층으로 실행하는 기본 서버."""

	daemon_threads = True
	app: Application

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
		ThreadingHTTPServer.__init__(
			self,
			(
				host,
				port,
			),
			ServerRequestHandler,
		)
		return

	def run(self) -> None:
		"""종료 시 수신 소켓까지 닫고 확장 기능의 종료를 보장한다."""
		with self:
			self.serve_forever(self.poll_interval)
		return

	def serve_forever(
		self,
		poll_interval: float = 0.5,
	) -> None:
		host = self.server_address[0]
		if not isinstance(host, str):
			raise TypeError('HTTP listen address must be a string')
		startup(
			self.application,
			'Python',
			host,
			self.server_port,
		)
		self.app.start()
		try:
			super().serve_forever(poll_interval=poll_interval)
		except KeyboardInterrupt:
			getLogger('DefEssential.Server').info('Shutdown requested by keyboard interrupt')
		finally:
			self.app.stop()
		return


class ServerRequestHandler(BaseHTTPRequestHandler):
	server: Server
	protocol_version = 'HTTP/1.1'
	server_version = 'DefEssential'
	logger = getLogger('DefEssential.Server')

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
		except ConnectionError as error:
			self.logger.warning('Client disconnected: %s', error)
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
			# 공통 처리기가 기록한 전송 오류는 연결 종료로 마무리한다.
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
		self.logger.info(
			'%s - %s',
			self.address_string(),
			format % args,
		)
		return
