from random import randrange
from time import sleep

from DefEssential import (
	Body,
	Request,
	RequestRunner,
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


class RunStreamIn(
	RequestRunner,
	method='PUT',
	url='/api/run/stream',
	body=Body(StreamContentReader()),
	tags='Streaming',
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
):
	"""받은 text·binary 메시지를 그대로 돌려보낸다."""

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
