from io import BytesIO
from sys import modules
from types import ModuleType
from unittest import TestCase

from DefStar import (
	Application,
	ClientError,
	Request,
	RequestReader,
	RequestRunner,
	Response,
)


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
		app.register(Sample)
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
		app.register(Dynamic)
		app.register(Static)
		self.assertEqual(
			app(request(uri='/sample/fixed')).body,
			b'static',
		)
		return

	def test_all_settings_and_execution_order(self):
		calls = []

		def check(name):
			def apply(request):
				calls.append(name)
				return
			return apply

		def body(request):
			calls.append('body')
			return 42

		def before(request):
			calls.append('request')
			return request, None

		def after(
			request,
			response,
		):
			calls.append('response')
			return response

		class Sample(
			RequestRunner,
			method='GET',
			url='/sample',
			origin=check('origin'),
			auth=check('auth'),
			parameters=check('parameters'),
			qs=check('qs'),
			headers=check('headers'),
			body=body,
			response={'200': 'sample'},
			summary='요약',
			description='설명',
			tags=['sample'],
			onRequest=[before, before],
			onResponse=after,
		):
			def run(
				self,
				request,
			):
				calls.append('run')
				return Response(body=str(request.body).encode())

		app = Application()
		app.register(Sample)
		self.assertEqual(
			app(request()).body,
			b'42',
		)
		self.assertEqual(
			calls,
			[
				'origin',
				'auth',
				'parameters',
				'qs',
				'headers',
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

		def before(request):
			return request, Response(status=403)

		class Sample(
			RequestRunner,
			method='GET',
			url='/sample',
			onRequest=before,
		):
			def run(
				self,
				request,
			):
				calls.append('run')
				return Response()

		app = Application()
		app.register(Sample)
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
		module = ModuleType('defstar_test_handlers')
		exec(
			'from DefStar import RequestRunner, Response\n'
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
		app.register(Sample)
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
		app.register(Sample)
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
		app.register(First)
		app.register(First)
		with self.assertRaises(ValueError):
			app.register(Second)
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

	def test_chunked_decoding_and_trailers(self):
		source = BytesIO(b'3;ext=value\r\nabc\r\n2\r\nde\r\n0\r\nX-End: yes\r\n\r\nNEXT')
		reader = RequestReader(
			source,
			chunked=True,
		)
		self.assertEqual(
			reader.read(2),
			b'ab',
		)
		self.assertEqual(
			reader.read(2),
			b'cd',
		)
		self.assertEqual(
			reader.read(),
			b'e',
		)
		self.assertTrue(reader.finished)
		self.assertEqual(
			source.read(),
			b'NEXT',
		)
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
				reader = RequestReader(
					BytesIO(payload),
					chunked=True,
				)
				with self.assertRaises(ClientError):
					reader.read()
		with self.assertRaises(ClientError):
			RequestReader(
				BytesIO(b'ab'),
				size=3,
			).read()
		return
