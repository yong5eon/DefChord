from http.client import (
	HTTPConnection,
	IncompleteRead,
)
from io import BytesIO
from socket import (
	create_connection,
	SHUT_RDWR,
	SO_LINGER,
	SOL_SOCKET,
)
from struct import pack
from threading import Event
from unittest import TestCase

from DefEssential import (
	Application,
	ApplicationRequest,
	ApplicationRequestError,
	ApplicationRequestResponse,
	Body,
	ClientError,
	Request,
	RequestRunnerRequestResponse,
	RequestRunner,
	Response,
	ResponseWriter,
)
from DefEssential.IO.Readers import (
	ChunkedStreamContentReader,
	StreamContentReader,
)
from DefEssential.IO.RequestReader import ClientDisconnected
from DefEssential.IO.Writers import (
	ChunkedStreamWriter,
	ServerSentEvents,
	ServerSentEventsWriter,
	StreamWriter,
)
from test_server import running


class WriterTests(TestCase):
	def writer(
		self,
		method='GET',
	):
		output = BytesIO()
		starts = []

		def send(
			response,
			chunked,
		):
			starts.append((
				response,
				chunked,
			))
			return

		return ResponseWriter(
			send,
			output,
			method=method,
		), output, starts

	def test_plain_stream_and_state_transitions(self):
		writer, output, starts = self.writer()
		stream = StreamWriter(writer)
		with self.assertRaises(RuntimeError):
			stream.write(b'before')
		with self.assertRaises(RuntimeError):
			stream.end()
		stream.begin(format='application/octet-stream')
		stream.write(b'abc')
		stream.flush()
		stream.write(b'def')
		stream.end()
		stream.end()
		self.assertEqual(
			output.getvalue(),
			b'abcdef',
		)
		self.assertEqual(
			len(starts),
			1,
		)
		with self.assertRaises(RuntimeError):
			stream.write(b'after')
		with self.assertRaises(RuntimeError):
			stream.begin()
		return

	def test_chunk_framing_empty_write_and_single_terminator(self):
		writer, output, starts = self.writer()
		stream = ChunkedStreamWriter(writer)
		stream.begin()
		stream.chunk(b'abc')
		stream.chunk(b'')
		stream.write(b'de')
		stream.end()
		stream.end()
		self.assertEqual(
			output.getvalue(),
			b'3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n',
		)
		self.assertTrue(starts[0][1])
		return

	def test_sse_with_plain_and_chunked_transport(self):
		for transport in (
			StreamWriter,
			ChunkedStreamWriter,
		):
			with self.subTest(transport=transport):
				writer, output, starts = self.writer()
				sse = ServerSentEventsWriter(transport(writer))
				sse.begin()
				sse.emit(
					'첫 줄\n\n끝',
					event='sample',
					id='42',
					retry=100,
				)
				sse.retry(200)
				sse.end()
				event = ServerSentEvents(
					data='첫 줄\n\n끝',
					event='sample',
					id='42',
					retry=100,
				).encode()
				retry = b'retry: 200\n\n'
				expected = event + retry
				if transport is ChunkedStreamWriter:
					expected = (
						format(len(event), 'x').encode() + b'\r\n' + event + b'\r\n'
						+ format(len(retry), 'x').encode() + b'\r\n' + retry + b'\r\n'
						+ b'0\r\n\r\n'
					)
				self.assertEqual(
					output.getvalue(),
					expected,
				)
				self.assertEqual(
					starts[0][0].header('Content-Type'),
					'text/event-stream; charset=utf-8',
				)
				self.assertEqual(
					starts[0][0].header('Cache-Control'),
					'no-cache',
				)
		return

	def test_sse_validates_before_writing(self):
		writer, output, _ = self.writer()
		sse = ServerSentEventsWriter(writer)
		sse.begin()
		for value in (
			-1,
			True,
		):
			with self.assertRaises(ValueError):
				sse.retry(value)
		with self.assertRaises(ValueError):
			sse.emit(
				'data',
				event='bad\nfield',
			)
		self.assertEqual(
			output.getvalue(),
			b'',
		)
		return

	def test_head_and_no_body_statuses_never_write_chunks(self):
		for method, status in (
			('HEAD', 200),
			('GET', 204),
			('GET', 205),
			('GET', 304),
		):
			with self.subTest(
				method=method,
				status=status,
			):
				writer, output, _ = self.writer(method)
				stream = ChunkedStreamWriter(writer)
				stream.begin(status=status)
				stream.chunk(b'not sent')
				stream.end()
				self.assertEqual(
					output.getvalue(),
					b'',
				)
		return

	def test_missing_transport_and_missing_response_are_errors(self):
		req = Request(
			'127.0.0.1',
			1,
			'GET',
			'/',
		)
		with self.assertRaises(RuntimeError):
			StreamWriter(req.writer)

		class Missing(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				return None

		app = Application()
		app.add(Missing)
		with self.assertRaises(TypeError):
			app(req)
		return

	def test_response_hook_applies_once_before_direct_headers(self):
		calls = []

		class After(RequestRunnerRequestResponse):
			def __call__(
				self,
				request,
				response,
			):
				calls.append('response')
				response.header(
					'X-Filtered',
					'yes',
				)
				return response

		class Direct(
			RequestRunner,
			method='GET',
			url='/',
			on_request_response=After(),
		):
			def run(
				self,
				request,
			):
				stream = StreamWriter(request.writer)
				stream.begin()
				stream.write(b'direct')
				return None

		writer, output, starts = self.writer()
		app = Application()
		app.add(Direct)
		result = app(Request(
			'127.0.0.1',
			1,
			'GET',
			'/',
			writer=writer,
		))
		self.assertIsNone(result)
		self.assertTrue(writer.ended)
		self.assertEqual(
			calls,
			['response'],
		)
		self.assertEqual(
			starts[0][0].header('X-Filtered'),
			'yes',
		)
		self.assertEqual(
			output.getvalue(),
			b'direct',
		)
		return

	def test_partial_writes_and_failure_do_not_finish_chunked_body(self):
		class Partial(BytesIO):
			def write(
				self,
				data,
			):
				return super().write(data[:2])

		source = Partial()
		writer = ResponseWriter(
			lambda response, chunked: None,
			source,
		)
		writer.begin(
			Response(),
			chunked=True,
		)
		writer.write(b'abc')
		writer.end()
		self.assertEqual(
			source.getvalue(),
			b'3\r\nabc\r\n0\r\n\r\n',
		)

		class Broken(BytesIO):
			def write(
				self,
				data,
			):
				raise BrokenPipeError('연결 종료')

		writer = ResponseWriter(
			lambda response, chunked: None,
			Broken(),
		)
		writer.begin(
			Response(),
			chunked=True,
		)
		with self.assertRaises(BrokenPipeError):
			writer.write(b'abc')
		self.assertTrue(writer.failed)
		with self.assertRaises(RuntimeError):
			writer.end()
		self.assertFalse(writer.ended)
		return

	def test_direct_headers_cannot_declare_length_or_body(self):
		for response in (
			Response(headers={'Content-Length': '3'}),
			Response(body=b'abc'),
		):
			writer, _, starts = self.writer()
			with self.assertRaises(ValueError):
				writer.begin(response)
			self.assertFalse(writer.started)
			self.assertEqual(
				starts,
				[],
			)
		return


class DirectServerTests(TestCase):
	def test_chunked_http10_rejected_before_response_starts(self):
		class Chunked(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				stream = ChunkedStreamWriter(request.writer)
				stream.begin()
				return None

		app = Application()
		app.add(Chunked)
		with running(app) as address:
			with create_connection(
				address,
				timeout=3,
			) as client:
				client.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
				with client.makefile('rb') as output:
					data = output.read()
				self.assertTrue(data.startswith(b'HTTP/1.1 400'))
				self.assertNotIn(
					b'Transfer-Encoding:',
					data,
				)
		return

	def test_response_hooks_cannot_replace_direct_output_body(self):
		class After(RequestRunnerRequestResponse):
			def __call__(
				self,
				request,
				response,
			):
				response.body = b'invalid filter body'
				return response

		class Direct(
			RequestRunner,
			method='GET',
			url='/',
			on_request_response=After(),
		):
			def run(
				self,
				request,
			):
				StreamWriter(request.writer).begin()
				return None

		app = Application()
		app.add(Direct)
		with self.assertLogs(
			'DefEssential.Server',
			level='ERROR',
		):
			with running(app) as address:
				connection = HTTPConnection(
					*address,
					timeout=3,
				)
				try:
					connection.request(
						'GET',
						'/',
					)
					response = connection.getresponse()
					self.assertEqual(
						response.status,
						500,
					)
					self.assertEqual(
						response.read(),
						b'Internal Server Error',
					)
				finally:
					connection.close()
		return

	def test_client_disconnect_propagates_and_releases_handler(self):
		release = Event()
		interrupted = Event()
		finished = Event()
		observed = Event()
		failures = []

		class RequestError(ApplicationRequestError):
			def __call__(
				self,
				request,
				error,
			):
				failures.append(error)
				observed.set()
				return

		class Events(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				sse = ServerSentEventsWriter(request.writer)
				sse.begin()
				sse.emit('first')
				try:
					if not release.wait(3):
						raise TimeoutError('연결 종료 신호가 없습니다')
					for _ in range(256):
						sse.emit('x' * 65536)
				except ConnectionError:
					interrupted.set()
					raise
				finally:
					finished.set()
				return None

		app = Application(on_request_error=RequestError())
		app.add(Events)
		with self.assertLogs(
			'DefEssential.Server',
			level='INFO',
		) as logged:
			with running(app) as address:
				client = create_connection(
					address,
					timeout=3,
				)
				try:
					client.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
					with client.makefile('rb') as output:
						while True:
							line = output.readline()
							if line == b'\r\n':
								break
							self.assertTrue(line)
						self.assertEqual(
							output.readline(),
							b'data: first\n',
						)
					client.shutdown(SHUT_RDWR)
					client.close()
					release.set()
					self.assertTrue(finished.wait(3))
					self.assertTrue(interrupted.is_set())
					self.assertTrue(observed.wait(3))
					self.assertIsInstance(failures[0], ConnectionError)
				finally:
					release.set()
					client.close()
		self.assertIn(
			'WARNING:DefEssential.Server:Client disconnected',
			'\n'.join(logged.output),
		)
		self.assertTrue(all(record.exc_info is None for record in logged.records))
		return

	def test_client_reset_while_receiving_body_is_logged_as_disconnect(self):
		reading = Event()
		observed = Event()
		failures = []

		class RequestError(ApplicationRequestError):
			def __call__(
				self,
				request,
				error,
			):
				failures.append(error)
				observed.set()
				return

		class Upload(
			RequestRunner,
			method='POST',
			url='/',
			body=Body(StreamContentReader()),
		):
			def run(
				self,
				request,
			):
				reading.set()
				request.reader.read()
				return Response()

		app = Application(on_request_error=RequestError())
		app.add(Upload)
		with self.assertLogs(
			'DefEssential.Server',
			level='INFO',
		) as logged:
			with running(app) as address:
				client = create_connection(
					address,
					timeout=3,
				)
				try:
					client.sendall(b'POST / HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/octet-stream\r\nContent-Length: 100\r\n\r\nabc')
					self.assertTrue(reading.wait(3))
					client.setsockopt(
						SOL_SOCKET,
						SO_LINGER,
						pack('ii', 1, 0),
					)
				finally:
					client.close()
				self.assertTrue(observed.wait(3))
		self.assertIsInstance(failures[0], ClientDisconnected)
		self.assertIn(
			'Client disconnected',
			'\n'.join(logged.output),
		)
		self.assertTrue(all(record.levelname == 'WARNING' and record.exc_info is None for record in logged.records))
		return

	def test_direct_output_before_handler_returns_and_other_requests_progress(self):
		for transport in (
			StreamWriter,
			ChunkedStreamWriter,
		):
			with self.subTest(transport=transport):
				release = Event()
				returned = Event()

				class Events(
					RequestRunner,
					method='GET',
					url='/events',
				):
					def run(
						self,
						request,
					):
						sse = ServerSentEventsWriter(transport(request.writer))
						sse.begin()
						sse.emit('first')
						if not release.wait(3):
							raise TimeoutError('종료 신호가 없습니다')
						sse.emit('last')
						sse.end()
						returned.set()
						return None

				class Normal(
					RequestRunner,
					method='GET',
					url='/normal',
				):
					def run(
						self,
						request,
					):
						return Response(body=b'ok')

				app = Application()
				app.add(Events)
				app.add(Normal)
				with running(app) as address:
					connection = HTTPConnection(
						*address,
						timeout=3,
					)
					normal = HTTPConnection(
						*address,
						timeout=3,
					)
					try:
						connection.request(
							'GET',
							'/events',
						)
						response = connection.getresponse()
						self.assertEqual(
							response.readline(),
							b'data: first\n',
						)
						self.assertFalse(returned.is_set())
						normal.request(
							'GET',
							'/normal',
						)
						self.assertEqual(
							normal.getresponse().read(),
							b'ok',
						)
						release.set()
						self.assertEqual(
							response.read(),
							b'\ndata: last\n\n',
						)
						self.assertTrue(returned.wait(1))
					finally:
						release.set()
						connection.close()
						normal.close()
		return

	def test_chunked_wire_format_and_automatic_end(self):
		class Chunked(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				stream = ChunkedStreamWriter(request.writer)
				stream.begin()
				stream.chunk(b'abc')
				stream.chunk(b'')
				stream.chunk(b'def')
				return None

		app = Application()
		app.add(Chunked)
		with running(app) as address:
			with create_connection(
				address,
				timeout=3,
			) as client:
				client.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
				with client.makefile('rb') as output:
					headers, body = output.read().split(b'\r\n\r\n', 1)
				self.assertIn(
					b'Transfer-Encoding: chunked',
					headers,
				)
				self.assertNotIn(
					b'Content-Length:',
					headers,
				)
				self.assertEqual(
					body,
					b'3\r\nabc\r\n3\r\ndef\r\n0\r\n\r\n',
				)
		return

	def test_error_before_begin_returns_normal_error_response(self):
		class Invalid(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				raise ClientError('잘못된 요청')

		app = Application()
		app.add(Invalid)
		with running(app) as address:
			connection = HTTPConnection(
				*address,
				timeout=3,
			)
			try:
				connection.request(
					'GET',
					'/',
				)
				response = connection.getresponse()
				self.assertEqual(
					response.status,
					400,
				)
				self.assertEqual(
					response.read().decode(),
					'잘못된 요청',
				)
			finally:
				connection.close()
		return

	def test_response_hooks_finish_before_body_transmission_failure(self):
		"""반환 이후 전송 실패와 본문 정리는 Application 훅의 관찰 대상이 아니다."""
		events = []
		errors = []

		class RequestHook(ApplicationRequest):
			def __call__(
				self,
				request,
			):
				events.append('request')
				return request

		class RequestResponse(ApplicationRequestResponse):
			def __call__(
				self,
				request,
				response,
			):
				self_test.assertFalse(request.writer.started)
				events.append('response')
				return response

		class RequestError(ApplicationRequestError):
			def __call__(
				self,
				request,
				error,
			):
				errors.append(error)
				return

		def body():
			try:
				events.append('transmission')
				yield b'first'
				raise ConnectionError('body transmission failed')
			finally:
				events.append('closed')
			return

		class Output(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				return Response(body=body())

		self_test = self
		app = Application(
			on_request=RequestHook(),
			on_request_response=RequestResponse(),
			on_request_error=RequestError(),
		)
		app.add(Output)
		with self.assertLogs(
			'DefEssential.Server',
			level='WARNING',
		) as logged:
			with running(app) as address:
				with create_connection(
					address,
					timeout=3,
				) as client:
					client.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
					with client.makefile('rb') as output:
						headers, received = output.read().split(b'\r\n\r\n', 1)
					self.assertIn(b'200', headers)
					self.assertIn(b'first', received)
		self.assertEqual(events, [
			'request',
			'response',
			'transmission',
			'closed',
		])
		self.assertEqual(errors, [])
		self.assertTrue(any('body transmission failed' in message for message in logged.output))
		return

	def test_error_after_begin_never_sends_second_response_or_final_chunk(self):
		for return_response in (
			False,
			True,
		):
			with self.subTest(return_response=return_response):
				class Invalid(
					RequestRunner,
					method='GET',
					url='/',
				):
					def run(
						self,
						request,
					):
						stream = ChunkedStreamWriter(request.writer)
						stream.begin()
						stream.chunk(b'first')
						if return_response:
							return Response(body=b'second')
						raise ClientError('출력 후 오류')

				app = Application()
				app.add(Invalid)
				with self.assertLogs(
					'DefEssential.Server',
					level='ERROR',
				):
					with running(app) as address:
						connection = HTTPConnection(
							*address,
							timeout=3,
						)
						try:
							connection.request(
								'GET',
								'/',
							)
							response = connection.getresponse()
							self.assertEqual(
								response.status,
								200,
							)
							with self.assertRaises(IncompleteRead) as caught:
								response.read()
							self.assertEqual(
								caught.exception.partial,
								b'first',
							)
						finally:
							connection.close()
		return

	def test_upload_and_direct_output_in_one_runner(self):
		class Echo(
			RequestRunner,
			method='PUT',
			url='/echo',
			body=Body(ChunkedStreamContentReader()),
		):
			def run(
				self,
				request,
			):
				stream = ChunkedStreamWriter(request.writer)
				stream.begin(format='application/octet-stream')
				while True:
					data = request.body.read(3)
					if not data:
						break
					stream.chunk(data)
				return None

		app = Application()
		app.add(Echo)
		with running(app) as address:
			connection = HTTPConnection(
				*address,
				timeout=3,
			)
			try:
				connection.request(
					'PUT',
					'/echo',
					body=iter((
						b'abc',
						b'def',
					)),
					headers={'Content-Type': 'application/octet-stream'},
					encode_chunked=True,
				)
				response = connection.getresponse()
				self.assertEqual(
					response.read(),
					b'abcdef',
				)
			finally:
				connection.close()
		return
