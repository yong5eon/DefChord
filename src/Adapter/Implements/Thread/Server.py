from http.server import (
	BaseHTTPRequestHandler,
	ThreadingHTTPServer,
)
from logging import getLogger
from typing import Optional

from ....Application import Application
from ....Error import Error
from ....Request import Request
from ....RequestReader import RequestReader
from ....Response import Response
from ....ResponseWriter import ResponseWriter
from ....Startup import startup


class Server(ThreadingHTTPServer):
	"""Provide a threaded development HTTP server without WSGI."""

	daemon_threads = True
	app: Application

	def serve_forever(
		self,
		poll_interval: float = 0.5,
	) -> None:
		self.app.start()
		try:
			startup(self)
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
		self.close_connection = True
		response = None
		request = None
		observations = []
		status = 500
		failure = None
		writer = ResponseWriter(
			self.begin_response,
			self.wfile,
			method=self.command,
			version=self.request_version,
		)
		try:
			try:
				reader = self.request_reader()
				request = Request(
					address=self.client_address[0],
					port=self.client_address[1],
					method=self.command,
					uri=self.path,
					headers=dict(self.headers.items()),
					reader=reader,
					writer=writer,
				)
				for extension in self.server.app.exts.values():
					context = extension.begin(request)
					observations.append((
						extension,
						context,
					))
				adapter = getattr(self.server, 'adapter', None)
				response = (
					adapter.application(request)
					if adapter is not None else self.server.app(request)
				)
			except Error as error:
				status = error.status
				failure = error
				if writer.started:
					raise
				response = Response(
					status=error.status,
					body=error.reason.encode('utf-8'),
					format='text/plain',
					charset='utf-8',
				)
			except Exception as error:
				failure = error
				if writer.started:
					raise
				self.logger.exception('Unexpected error while handling request')
				response = Response(
					status=500,
					body=b'Internal Server Error',
				)
			if response is not None:
				status = response.status
				writer.response(
					response,
					filtered=True,
				)
			elif not writer.ended:
				raise RuntimeError('Response was neither returned nor completed successfully')
			else:
				status = self.response_status
		except (ConnectionError, OSError) as error:
			failure = error
			self.logger.info('Connection closed while sending response', exc_info=True)
		except Exception as error:
			failure = error
			self.logger.exception('Response transmission failed: closing connection without another error response')
		finally:
			if response is not None:
				try:
					response.close()
				except Exception as error:
					failure = error
					self.logger.exception('Response body cleanup failed')
			if request is not None:
				for extension, context in reversed(observations):
					try:
						extension.end(
							request,
							context,
							status,
							failure,
						)
					except Exception:
						self.logger.exception('Extension request observation cleanup failed')
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
		for key, value in response.headers():
			if key.lower() not in (
				'connection',
				'content-length',
				'transfer-encoding',
			):
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


def serve(
	host: str,
	port: int,
	app: Application,
) -> Server:
	"""Create and return a server; the caller manages serving and shutdown."""
	server = Server(
		(
			host,
			port,
		),
		ServerRequestHandler,
	)
	server.app = app
	return server
