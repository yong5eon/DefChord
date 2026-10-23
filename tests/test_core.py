from io import BytesIO
from sys import modules
from types import ModuleType
from unittest import TestCase

from DefEssential import (
	Application,
	ClientError,
	Error,
	Body,
	Request,
	RequestFilter,
	RequestReader,
	RequestRunner,
	Response,
	ResponseFilter,
	ServerError,
)
from DefEssential.IO.Readers import (
	ChunkedStream,
	TextContentReader,
)
from DefEssential.IO.RequestReader import ClientDisconnected


def request(
	method='GET',
	uri='/sample',
	body=b'',
	headers=None,
):
	return Request(
		address='127.0.0.1',
		port=1234,
		method=method,
		uri=uri,
		headers=headers,
		reader=RequestReader(
			BytesIO(body),
			size=len(body),
		),
	)


class CoreTests(TestCase):
	def test_server_error_status_and_reason(self):
		error = ServerError('처리 실패')
		self.assertIsInstance(error, Error)
		self.assertEqual(error.status, 500)
		self.assertEqual(error.message, 'Internal Server Error')
		self.assertEqual(error.reason, '처리 실패')
		self.assertEqual(str(error), '처리 실패')
		error = ServerError('일시적으로 사용할 수 없음', status=503)
		self.assertEqual(error.status, 503)
		self.assertEqual(error.message, 'Service Unavailable')
		for status in (
			499,
			600,
		):
			with self.subTest(status=status):
				with self.assertRaises(ValueError):
					ServerError('잘못된 상태 코드', status=status)
		return

	def test_custom_method_and_request_lifetime(self):
		instances = []

		class Sample(
			RequestRunner,
			method='CUSTOM',
			url='/sample/:id',
		):
			def __init__(self):
				instances.append(self)
				return

			def run(
				self,
				request,
			):
				return Response(body=request.parameters['id'].encode())

		app = Application()
		self.assertEqual(
			app.router.routes,
			[],
		)
		app.add(Sample)
		for _ in range(2):
			response = app(request(
				'CUSTOM',
				'/sample/42',
			))
			self.assertEqual(
				response.body,
				b'42',
			)
		self.assertEqual(
			len(instances),
			2,
		)
		self.assertIsNot(
			instances[0],
			instances[1],
		)
		return

	def test_static_path_priority(self):
		class Dynamic(
			RequestRunner,
			method='GET',
			url='/sample/:id',
		):
			def run(
				self,
				request,
			):
				return Response(body=b'dynamic')

		class Static(
			RequestRunner,
			method='GET',
			url='/sample/fixed',
		):
			def run(
				self,
				request,
			):
				return Response(body=b'static')

		app = Application()
		app.add(Dynamic)
		app.add(Static)
		self.assertEqual(
			app(request(uri='/sample/fixed')).body,
			b'static',
		)
		return

	def test_all_settings_and_execution_order(self):
		calls = []

		class SampleBody(Body):
			def __init__(self):
				super().__init__(TextContentReader())
				return

			def __call__(self, request):
				calls.append('body')
				return 42

		class Before(RequestFilter):
			def __call__(self, request):
				calls.append('request')
				return request, None

		class After(ResponseFilter):
			def __call__(self, request, response):
				calls.append('response')
				return response

		class Sample(
			RequestRunner,
			method='GET',
			url='/sample',
			body=SampleBody(),
			response={'200': 'sample'},
			summary='요약',
			description='설명',
			tags=['sample'],
			onRequest=[Before(), Before()],
			onResponse=After(),
		):
			def run(
				self,
				request,
			):
				calls.append('run')
				return Response(body=str(request.body).encode())

		app = Application()
		app.add(Sample)
		self.assertEqual(
			app(request()).body,
			b'42',
		)
		self.assertEqual(
			calls,
			[
				'body',
				'request',
				'request',
				'run',
				'response',
			],
		)
		self.assertEqual(
			Sample.properties.summary,
			'요약',
		)
		self.assertEqual(
			Sample.properties.response,
			{'200': 'sample'},
		)
		return

	def test_request_filter_short_circuit(self):
		calls = []

		class Before(RequestFilter):
			def __call__(self, request):
				return request, Response(status=403)

		class Sample(
			RequestRunner,
			method='GET',
			url='/sample',
			onRequest=Before(),
		):
			def run(
				self,
				request,
			):
				calls.append('run')
				return Response()

		app = Application()
		app.add(Sample)
		self.assertEqual(
			app(request()).status,
			403,
		)
		self.assertEqual(
			calls,
			[],
		)
		return

	def test_module_load_is_independent_and_idempotent(self):
		module = ModuleType('defessential_test_handlers')
		exec(
			'from DefEssential import RequestRunner, Response\n'
			'class Sample(RequestRunner, method="GET", url="/sample"):\n'
			'\tdef run(self, request):\n'
			'\t\treturn Response(body=b"loaded")\n',
			module.__dict__,
		)
		modules[module.__name__] = module
		self.addCleanup(
			modules.pop,
			module.__name__,
		)
		first = Application()
		second = Application()
		first.load(module.__name__)
		first.load(module.__name__)
		second.load(module.__name__)
		self.assertEqual(
			len(first.router.routes),
			1,
		)
		self.assertEqual(
			second(request()).body,
			b'loaded',
		)
		first.router.routes.clear()
		self.assertEqual(
			len(second.router.routes),
			1,
		)
		return

	def test_not_found_and_method_not_allowed(self):
		class Sample(
			RequestRunner,
			method='GET',
			url='/sample',
		):
			def run(
				self,
				request,
			):
				return Response()

		app = Application()
		app.add(Sample)
		for req, status in (
			(request(uri='/missing'), 404),
			(request(method='POST'), 405),
		):
			with self.assertRaises(ClientError) as caught:
				app(req)
			self.assertEqual(
				caught.exception.status,
				status,
			)
		return

	def test_missing_content_type(self):
		class Sample(
			RequestRunner,
			method='POST',
			url='/sample',
		):
			def run(
				self,
				request,
			):
				return Response()

		app = Application()
		app.add(Sample)
		with self.assertRaises(ClientError):
			app(request(
				method='POST',
				body=b'body',
			))
		return

	def test_invalid_declarations_and_duplicate_routes(self):
		for method in (
			'GET POST',
			'',
			'한글',
		):
			with self.assertRaises(ValueError):
				type(
					'Invalid',
					(RequestRunner,),
					{},
					method=method,
					url='/sample',
				)
		with self.assertRaises(TypeError):
			type(
				'Invalid',
				(RequestRunner,),
				{},
				method='GET',
			)
		def run(self, request):
			return Response()

		for declaration in (
			{'origin': lambda request: None},
			{'auth': lambda request: None},
			{'parameters': lambda request: None},
			{'qs': lambda request: None},
			{'headers': lambda request: None},
			{'body': lambda request: None},
			{'onRequest': lambda request: (request, None)},
			{'onResponse': lambda request, response: response},
		):
			with self.subTest(declaration=tuple(declaration)):
				with self.assertRaises(TypeError):
					type(
						'InvalidContract',
						(RequestRunner,),
						{'run': run},
						method='GET',
						url='/invalid',
						**declaration,
					)

		class First(
			RequestRunner,
			method='GET',
			url='/sample',
		):
			def run(
				self,
				request,
			):
				return Response()

		class Second(
			First,
			method='GET',
			url='/sample',
		):
			pass

		app = Application()
		app.add(First)
		app.add(First)
		with self.assertRaises(ValueError):
			app.add(Second)
		return


class ReaderTests(TestCase):
	def test_content_length_stops_at_boundary(self):
		source = BytesIO(b'bodyNEXT')
		reader = RequestReader(
			source,
			size=4,
		)
		self.assertEqual(
			reader.read(2),
			b'bo',
		)
		self.assertEqual(
			reader.read(),
			b'dy',
		)
		self.assertEqual(
			reader.read(),
			b'',
		)
		self.assertEqual(
			source.read(),
			b'NEXT',
		)
		return

	def test_chunked_body_requires_chunked_stream(self):
		reader = RequestReader(
			BytesIO(b'3\r\nabc\r\n0\r\n\r\n'),
			chunked=True,
		)
		with self.assertRaises(ClientError) as caught:
			reader.read()
		self.assertEqual(caught.exception.status, 411)
		with self.assertRaises(ValueError):
			ChunkedStream(RequestReader(
				BytesIO(b'abc'),
				size=3,
			))
		return

	def test_chunked_decoding_and_trailers(self):
		source = BytesIO(b'3;ext=value\r\nabc\r\n2\r\nde\r\n0\r\nX-End: yes\r\n\r\nNEXT')
		reader = RequestReader(
			source,
			chunked=True,
		)
		stream = ChunkedStream(reader)
		self.assertEqual(
			stream.read(2),
			b'ab',
		)
		self.assertEqual(
			stream.read(2),
			b'cd',
		)
		self.assertEqual(
			stream.read(),
			b'e',
		)
		self.assertTrue(stream.finished)
		self.assertTrue(reader.finished)
		self.assertEqual(
			source.read(),
			b'NEXT',
		)
		return

	def test_chunk_reads_do_not_cross_chunk_boundaries(self):
		stream = ChunkedStream(RequestReader(
			BytesIO(b'3\r\nabc\r\n2\r\nde\r\n0\r\n\r\nNEXT'),
			chunked=True,
		))
		self.assertEqual(
			stream.read(1),
			b'a',
		)
		self.assertEqual(
			stream.chunk(),
			b'bc',
		)
		self.assertEqual(
			stream.chunk(0),
			b'',
		)
		self.assertEqual(
			stream.chunk(10),
			b'de',
		)
		self.assertEqual(
			stream.chunk(),
			b'',
		)
		self.assertTrue(stream.finished)
		with self.assertRaises(ValueError):
			stream.chunk(-2)
		return

	def test_malformed_and_interrupted_inputs(self):
		for payload in (
			b'X\r\n',
			b' 3\r\nabc\r\n',
			b'3\r\nab',
			b'3\r\nabcXX',
			b'0\r\nContent-Length: 1\r\n\r\n',
			b'0\r\n',
		):
			with self.subTest(payload=payload):
				stream = ChunkedStream(RequestReader(
					BytesIO(payload),
					chunked=True,
				))
				with self.assertRaises(ClientError):
					stream.read()
		with self.assertRaises(ClientError):
			RequestReader(
				BytesIO(b'ab'),
				size=3,
			).read()
		return
	def test_socket_errors_are_client_disconnects(self):
		class Disconnected:
			def read(
				self,
				size=-1,
			):
				raise ConnectionResetError('reset by peer')

			def readline(
				self,
				size=-1,
			):
				raise ConnectionAbortedError('aborted')

		for chunked, size in (
			(False, 3),
			(True, None),
		):
			with self.subTest(chunked=chunked):
				reader = RequestReader(
					Disconnected(),
					size=size,
					chunked=chunked,
				)
				with self.assertRaises(ClientDisconnected) as raised:
					(ChunkedStream(reader) if chunked else reader).read()
				self.assertIsInstance(raised.exception.__cause__, ConnectionError)
		return
