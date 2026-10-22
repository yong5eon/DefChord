from random import randrange
from time import sleep

from DefEssential import (
	Body,
	Headers,
	Request,
	RequestRunner,
)
from DefEssential.Readers import StreamContentReader
from DefEssential.Validator.Patterns import (
	IsIn,
	IsString,
	ToInteger,
)
from DefEssential.Writers import (
	ChunkedStreamWriter,
	ServerSentEventsWriter,
	StreamWriter,
)


def echo(request: Request) -> None:
	writer = ChunkedStreamWriter(request.writer)
	writer.begin(format='application/octet-stream')
	while True:
		data = request.body.read(65536)
		if not data:
			break
		writer.chunk(data)
	writer.end()
	return


class RunStreamIn(
	RequestRunner,
	method='PUT',
	url='/api/run/stream',
	headers=Headers(
		{'Content-Length': ToInteger()},
		requires='Content-Length',
	),
	body=Body(StreamContentReader()),
	tags='Streaming',
):
	def run(
		self,
		request: Request,
	) -> None:
		echo(request)
		return


class RunChunkedStreamIn(
	RequestRunner,
	method='PUT',
	url='/api/run/stream/chunked',
	headers=Headers(
		{'Transfer-Encoding': IsString(IsIn('chunked'))},
		requires='Transfer-Encoding',
	),
	body=Body(StreamContentReader()),
	tags='Streaming',
):
	def run(
		self,
		request: Request,
	) -> None:
		echo(request)
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
