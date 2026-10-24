from logging import getLogger
from random import randrange
from time import sleep

from DefEssential import (
	Body,
	Request,
	RequestRunner,
	RequestRunnerRequest,
	RequestRunnerRequestError,
	RequestRunnerRequestResponse,
	Response,
)
from DefEssential.IO.Readers import (
	ChunkedStreamContentReader,
	StreamContentReader,
)
from DefEssential.IO.WebSocket import WebSocket
from DefEssential.IO.Writers import (
	ChunkedStreamWriter,
	ServerSentEventsWriter,
	StreamWriter,
)


class StreamingRequestLog(RequestRunnerRequest):
	"""Log the request after body processing and immediately before the handler runs."""

	def __call__(
		self,
		request: Request,
	) -> Request:
		getLogger('Sample.Streaming').debug(
			'요청 훅: id=%s (핸들러 실행 전)',
			request.id,
		)
		return request


class StreamingResponseHeaders(RequestRunnerRequestResponse):
	"""Modify the response before headers are sent when the stream begins."""

	def __call__(
		self,
		request: Request,
		response: Response,
	) -> Response:
		response.header(
			'X-Request-ID',
			request.id,
		)
		getLogger('Sample.Streaming').debug(
			'응답 훅: id=%s status=%s (헤더 전송 전)',
			request.id,
			response.status,
		)
		return response


class StreamingErrorLog(RequestRunnerRequestError):
	"""Observe streaming errors by request ID and exception type."""

	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> None:
		getLogger('Sample.Streaming').debug(
			'오류 훅: id=%s error_type=%s',
			request.id,
			type(error).__name__,
		)
		return


class RunStreamIn(
	RequestRunner,
	method='PUT',
	url='/api/run/stream',
	body=Body(StreamContentReader()),
	tags='Streaming',
	on_request=StreamingRequestLog(),
	on_request_response=StreamingResponseHeaders(),
	on_request_error=StreamingErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> None:
		writer = ChunkedStreamWriter(request.writer)
		writer.begin(format='application/octet-stream')
		while True:
			data = request.body.read(65536)
			if not data:
				break
			writer.chunk(data)
		writer.end()
		return


class RunChunkedStreamIn(
	RequestRunner,
	method='PUT',
	url='/api/run/stream/chunked',
	body=Body(ChunkedStreamContentReader()),
	tags='Streaming',
	on_request=StreamingRequestLog(),
	on_request_response=StreamingResponseHeaders(),
	on_request_error=StreamingErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> None:
		writer = ChunkedStreamWriter(request.writer)
		writer.begin(format='application/octet-stream')
		while True:
			data = request.body.chunk(65536)
			if not data:
				break
			writer.chunk(data)
		writer.end()
		return


class RunStreamOut(
	RequestRunner,
	method='GET',
	url='/api/run/stream',
	tags='Streaming',
	on_request=StreamingRequestLog(),
	on_request_response=StreamingResponseHeaders(),
	on_request_error=StreamingErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> None:
		writer = StreamWriter(request.writer)
		writer.begin(
			format='text/plain',
			charset='utf-8',
		)
		for i in range(10):
			writer.write(str(i).encode('ascii'))
			writer.flush()
			sleep(1)
		writer.end()
		return


class RunChunkedStreamOut(
	RequestRunner,
	method='GET',
	url='/api/run/stream/chunked',
	tags='Streaming',
	on_request=StreamingRequestLog(),
	on_request_response=StreamingResponseHeaders(),
	on_request_error=StreamingErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> None:
		writer = ChunkedStreamWriter(request.writer)
		writer.begin(
			format='text/plain',
			charset='utf-8',
		)
		for i in range(10):
			writer.chunk(str(i).encode('ascii'))
			sleep(1)
		writer.end()
		return


class RunServerSentEvent(
	RequestRunner,
	method='GET',
	url='/api/run/stream/sse',
	tags='Streaming',
	on_request=StreamingRequestLog(),
	on_request_response=StreamingResponseHeaders(),
	on_request_error=StreamingErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> None:
		writer = ServerSentEventsWriter(request.writer)
		writer.begin()
		while True:
			value = randrange(1, 1000)
			writer.emit(
				str(value),
				id=str(value),
			)
			if value % 5 == 0:
				writer.retry(1000)
			sleep(1)


class RunWebSocket(
	RequestRunner,
	method='GET',
	url='/api/run/ws',
	tags='Streaming',
	on_request=StreamingRequestLog(),
	on_request_response=StreamingResponseHeaders(),
	on_request_error=StreamingErrorLog(),
):
	"""Echo received text and binary messages."""

	def run(
		self,
		request: Request,
	) -> None:
		socket = WebSocket(
			request,
			limit=65536,
		)
		socket.accept('echo' if 'echo' in socket.protocols else None)
		while True:
			message = socket.receive()
			if message is None:
				break
			socket.send(message)
		return
