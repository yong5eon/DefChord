from contextlib import redirect_stdout
from dataclasses import dataclass
from http.client import HTTPConnection
from importlib import import_module
from io import StringIO
from json import loads
from threading import Event
from typing import (
	Annotated,
	Any,
)
from unittest import TestCase
from unittest.mock import patch

from DefEssential import (
	Application,
	Auth,
	Body,
	ClientError,
	Content,
	Extension,
	Headers,
	Parameters,
	QueryString,
	RequestRunner,
	Response,
	ResponseSpec,
)
from DefEssential.Credentials import (
	Header,
	HTTP,
	OAuth2Password,
)
from DefEssential.Descriptor import (
	Integer,
	Object,
	Properties,
	Schema,
	String,
	ToSchema,
)
from DefEssential.Extensions import (
	Status,
	Ping,
	Metrics,
	Spec,
	Swagger,
)
from DefEssential.Readers import JavaScriptObjectNotationContentReader
from DefEssential.Validator.Patterns import ToInteger
from DefEssential.Writers import ChunkedStreamWriter

from test_features import (
	SessionAuthorization,
	request,
)
from test_server import running


class Echo(
	RequestRunner,
	method='GET',
	url='/echo/:id',
):
	def run(
		self,
		req,
	):
		return Response(body=req.parameters['id'].encode())


class ExtensionTests(TestCase):
	def get(
		self,
		address,
		path,
		headers=None,
	):
		connection = HTTPConnection(
			*address,
			timeout=3,
		)
		try:
			connection.request(
				'GET',
				path,
				headers=headers or {},
			)
			response = connection.getresponse()
			return response.status, dict(response.getheaders()), response.read()
		finally:
			connection.close()

	def test_real_http_extensions_startup_and_application_isolation(self):
		metrics = Metrics('/metrics')
		spec = Spec('/spec')
		app = Application(exts=(
			Status('/status', title='<DefEssential>'),
			Swagger('/swagger'),
			metrics,
			spec,
			Ping('/ping'),
		))
		app.register(Echo)
		other = Application(exts=(Spec('/spec'),))
		with redirect_stdout(StringIO()) as output:
			with running(app) as address:
				for path, expected in (
					('/ping', 'application/json'),
					('/metrics', 'text/plain'),
					('/spec', 'application/json'),
					('/status', 'text/html'),
					('/swagger', 'text/html'),
				):
					status, headers, body = self.get(address, path)
					self.assertEqual(status, 200, body)
					self.assertTrue(headers['Content-Type'].startswith(expected))
				self.assertTrue(app.running)
				status, headers, body = self.get(address, '/echo/hello')
				self.assertEqual(body, b'hello')
				status, headers, body = self.get(address, '/status', {'Accept': 'application/json'})
				self.assertIn('GET /echo/:id', loads(body)['requests'])
				status, headers, body = self.get(address, '/swagger')
				self.assertIn(b'data-spec-url="/spec"', body)
				self.assertIn(b'SwaggerUIBundle', body)
				status, headers, body = self.get(address, '/status')
				self.assertIn(b'&lt;DefEssential&gt;', body)
				self.assertIn(b'<title>&lt;DefEssential&gt; Status</title>', body)
				self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
				status, headers, body = self.get(address, '/ping')
				self.assertEqual(status, 200)
				self.assertEqual(loads(body), {'status': 'running'})
		self.assertFalse(app.running)
		self.assertIn('Extensions: 5 extensions', output.getvalue())
		self.assertIn(f'http://127.0.0.1:{address[1]}/swagger', output.getvalue())
		self.assertEqual(spec.document(other)['paths'], {})
		self.assertNotIn('/spec', spec.document(app)['paths'])
		ping = Ping('/state').handle(app, request())
		assert isinstance(ping.body, bytes)
		self.assertEqual(ping.status, 503)
		self.assertEqual(loads(ping.body)['status'], 'stopped')
		return

	def test_dependency_collision_and_instance_ownership(self):
		for extensions in (
			(Status('/status'),),
			(Swagger('/swagger'),),
			(Metrics('/same'), Spec('/same')),
			(Metrics('/a'), Metrics('/b'), Status('/status')),
			(Spec('/a'), Spec('/b'), Swagger('/swagger')),
		):
			with self.assertRaises(ValueError):
				Application(exts=extensions)
		extension = Metrics('/metrics')
		Application(exts=(extension,))
		with self.assertRaises(ValueError):
			Application(exts=(extension,))

		class Conflict(
			RequestRunner,
			method='GET',
			url='/metrics',
		):
			def run(self, req):
				return Response()

		app = extension.application
		assert app is not None
		with self.assertRaises(ValueError):
			app.register(Conflict)
		with self.assertRaises(ValueError):
			Metrics('/:variable')
		return

	def test_lifecycle_order_rollback_and_failures_are_explicit(self):
		events = []

		class Lifecycle(Extension):
			def start(self, app):
				events.append('start:' + self.path)

			def stop(self, app):
				events.append('stop:' + self.path)

			def handle(self, app, req):
				return Response()

		class Failing(Lifecycle):
			def start(self, app):
				raise ValueError('시작 실패')

		app = Application(exts=(
			Lifecycle('/first'),
			Lifecycle('/last'),
		))
		app.start()
		with self.assertRaises(RuntimeError):
			app.start()
		with self.assertRaises(RuntimeError):
			app.register(Echo)
		app.stop()
		app.stop()
		self.assertEqual(events, ['start:/first', 'start:/last', 'stop:/last', 'stop:/first'])
		events.clear()
		app = Application(exts=(
			Lifecycle('/first'),
			Failing('/fail'),
		))
		with self.assertRaises(ValueError):
			app.start()
		self.assertFalse(app.running)
		self.assertEqual(events, ['start:/first', 'stop:/first'])
		return

	def test_swagger_spec_binding_escaping_headers_and_head(self):
		swagger = Swagger('/swagger', title='<DefEssential>', description='</script>')
		spec = Spec('/custom-spec')
		app = Application(exts=(
			swagger,
			spec,
		))
		response = app(request('/swagger'))
		assert isinstance(response, Response)
		assert isinstance(response.body, bytes)
		self.assertIn(b'data-spec-url="/custom-spec"', response.body)
		self.assertIn(b'&lt;DefEssential&gt;', response.body)
		self.assertIn(b'&lt;/script&gt;', response.body)
		self.assertIn(b'validatorUrl: null', response.body)
		self.assertIn(b'persistAuthorization: false', response.body)
		self.assertIn(b'swagger-ui-dist@5.32.0/', response.body)
		self.assertNotIn(b'<header>', response.body)
		self.assertNotIn(b'<h1>', response.body)
		self.assertIn(b'--ui-font:', response.body)
		self.assertIn(b'--code-font:', response.body)
		self.assertIn(b'id="error-message"', response.body)
		self.assertEqual(response.header('Cache-Control'), 'no-store')
		policy = response.header('Content-Security-Policy')
		assert isinstance(policy, str)
		self.assertIn("connect-src 'self'", policy)
		self.assertIn('https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/', policy)
		self.assertNotIn('/swagger', spec.document(app)['paths'])
		response = app(request('/swagger', headers={'Accept': 'application/json'}))
		assert isinstance(response, Response)
		content_type = response.header('Content-Type')
		assert isinstance(content_type, str)
		self.assertTrue(content_type.startswith('text/html'))
		with redirect_stdout(StringIO()):
			with running(app) as address:
				connection = HTTPConnection(*address, timeout=3)
				try:
					connection.request('HEAD', '/swagger')
					response = connection.getresponse()
					self.assertEqual(response.status, 200)
					self.assertEqual(response.read(), b'')
				finally:
					connection.close()
		return

	def test_swagger_invalid_settings_and_unbound_use(self):
		invalid_settings: tuple[dict[str, Any], ...] = (
			{'title': ''},
			{'title': None},
			{'description': None},
		)
		for settings in invalid_settings:
			with self.subTest(settings=settings):
				with self.assertRaises(ValueError):
					Swagger('/swagger', **settings)
		with self.assertRaises(RuntimeError):
			Swagger('/swagger').handle(Application(), request('/swagger'))
		return

	def test_metrics_windows_and_unmatched_cardinality(self):
		metrics_module = import_module('DefEssential.Extensions.Metrics')
		metrics = Metrics('/metrics')
		app = Application(exts=(metrics,))
		app.register(Echo)
		with patch.object(metrics_module, 'monotonic', return_value=100.0):
			app.start()
			req = request('/echo/one')
			context = metrics.begin(req)
			self.assertEqual(metrics.snapshot(app)['requests']['GET /echo/:id']['active'], 1)
		with patch.object(metrics_module, 'monotonic', return_value=102.0):
			metrics.end(req, context, 200, None)
		with patch.object(metrics_module, 'monotonic', return_value=103.0):
			stats = metrics.snapshot(app)['requests']['GET /echo/:id']
			self.assertEqual(stats['windows']['1']['success'], 1)
			self.assertEqual(stats['windows']['1']['max_duration'], 2.0)
			self.assertEqual(stats['duration'], 2.0)
		for uri in (
			'/unknown-one',
			'/unknown-two',
		):
			req = request(uri)
			context = metrics.begin(req)
			metrics.end(req, context, 404, None)
		self.assertEqual(metrics.snapshot(app)['requests']['<unmatched>']['failure'], 2)
		self.assertNotIn('/unknown-one', metrics.requests)
		self.assertIn('route="GET /echo/:id"', metrics.render(app))
		app.stop()
		return

	def test_metrics_stream_active_until_transmission_finishes_and_error(self):
		release = Event()
		done = Event()
		metrics = Metrics('/metrics')

		class Stream(
			RequestRunner,
			method='GET',
			url='/stream',
		):
			def run(self, req):
				def parts():
					yield b'first'
					if not release.wait(3):
						raise TimeoutError('테스트 스트림 종료 신호 없음')
					yield b'last'
				return Response(body=parts())

		class Invalid(
			RequestRunner,
			method='GET',
			url='/error',
		):
			def run(self, req):
				raise ClientError('요청 오류')

		class SignalMetrics(Metrics):
			def end(self, req, context, status, error):
				super().end(req, context, status, error)
				done.set()
				return

		metrics = SignalMetrics('/metrics')
		app = Application(exts=(metrics,))
		app.register(Stream)
		app.register(Invalid)
		with redirect_stdout(StringIO()):
			with running(app) as address:
				connection = HTTPConnection(*address, timeout=3)
				try:
					connection.request('GET', '/stream')
					response = connection.getresponse()
					self.assertEqual(response.read(5), b'first')
					self.assertEqual(metrics.snapshot(app)['requests']['GET /stream']['active'], 1)
					release.set()
					self.assertEqual(response.read(), b'last')
					self.assertTrue(done.wait(3))
					self.assertEqual(metrics.snapshot(app)['requests']['GET /stream']['success'], 1)
					done.clear()
					self.assertEqual(self.get(address, '/error')[0], 400)
					self.assertTrue(done.wait(3))
					self.assertEqual(metrics.snapshot(app)['requests']['GET /error']['failure'], 1)
				finally:
					release.set()
					connection.close()
		return

	def test_metrics_direct_output_status_and_failed_stream(self):
		done = Event()

		class SignalMetrics(Metrics):
			def end(self, req, context, status, error):
				super().end(req, context, status, error)
				done.set()
				return

		class Direct(
			RequestRunner,
			method='GET',
			url='/direct',
		):
			def run(self, req):
				writer = ChunkedStreamWriter(req.writer)
				writer.begin(status=400)
				writer.chunk(b'bad')
				return None

		metrics = SignalMetrics('/metrics')
		app = Application(exts=(metrics,))
		app.register(Direct)
		with redirect_stdout(StringIO()):
			with running(app) as address:
				self.assertEqual(self.get(address, '/direct')[0], 400)
				self.assertTrue(done.wait(3))
				self.assertEqual(metrics.snapshot(app)['requests']['GET /direct']['failure'], 1)
		return

	def test_metrics_stream_failure_is_not_success(self):
		done = Event()

		class SignalMetrics(Metrics):
			def end(self, req, context, status, error):
				super().end(req, context, status, error)
				done.set()
				return

		class Broken(
			RequestRunner,
			method='GET',
			url='/broken',
		):
			def run(self, req):
				def parts():
					yield b'partial'
					raise ValueError('스트림 생성 오류')
				return Response(body=parts())

		metrics = SignalMetrics('/metrics')
		app = Application(exts=(metrics,))
		app.register(Broken)
		with redirect_stdout(StringIO()):
			with self.assertLogs('DefEssential.Server', level='ERROR'):
				with running(app) as address:
					self.assertEqual(self.get(address, '/broken')[2], b'partial')
					self.assertTrue(done.wait(3))
					stats = metrics.snapshot(app)['requests']['GET /broken']
					self.assertEqual(stats['failure'], 1)
					self.assertEqual(stats['success'], 0)
					self.assertEqual(stats['active'], 0)
		return


class SpecTests(TestCase):
	def test_openapi_metadata_schema_auth_and_custom_methods(self):
		@dataclass
		class Model:
			value: Annotated[int, '값']

		class Documented(
			RequestRunner,
			method='POST',
			url='/items/:id',
			summary='항목 생성',
			description='본문을 검증한다',
			tags=(
				'Items',
				'Write',
			),
			parameters=Parameters(
				{'id': ToInteger()},
				format={'id': Integer(min=1)},
			),
			qs=QueryString(
				{},
				requires='limit',
				format={'limit': Integer(default=5, required=False)},
			),
			headers=Headers(
				{},
				requires='X-Required',
				format={'X-Required': String(min=2, max=8, enum=('yes', 'no'))},
			),
			body=Body(
				JavaScriptObjectNotationContentReader(),
				content=Content(
					'application/json',
					Object(properties=Properties(value=Integer(min=0, max=10))),
					{'value': 1},
				),
			),
			response=ResponseSpec(
				201,
				'생성됨',
				Content('application/json', ToSchema(Model)),
			),
			auth=Auth(
				SessionAuthorization(),
				HTTP('Bearer'),
				optional=True,
			),
		):
			def run(self, req):
				return Response(status=201)

		class Custom(
			RequestRunner,
			method='CUSTOM',
			url='/custom',
		):
			def run(self, req):
				return Response()

		spec = Spec('/spec')
		app = Application(exts=(spec,))
		app.register(Documented)
		app.register(Custom)
		document = spec.document(app)
		operation = document['paths']['/items/{id}']['post']
		self.assertEqual(operation['summary'], '항목 생성')
		self.assertEqual(operation['description'], '본문을 검증한다')
		self.assertEqual(operation['tags'], ['Items', 'Write'])
		self.assertEqual(operation['security'], [{'HTTP': []}, {}])
		parameters = {(item['in'], item['name']): item for item in operation['parameters']}
		self.assertTrue(parameters['path', 'id']['required'])
		self.assertEqual(parameters['path', 'id']['schema']['minimum'], 1)
		self.assertTrue(parameters['query', 'limit']['required'])
		self.assertEqual(parameters['query', 'limit']['schema']['default'], 5)
		self.assertTrue(parameters['header', 'X-Required']['required'])
		self.assertEqual(parameters['header', 'X-Required']['schema']['minLength'], 2)
		self.assertEqual(parameters['header', 'X-Required']['schema']['maxLength'], 8)
		self.assertEqual(parameters['header', 'X-Required']['schema']['enum'], ['yes', 'no'])
		self.assertEqual(operation['requestBody']['content']['application/json']['example'], {'value': 1})
		self.assertIn('Model', document['components']['schemas'])
		self.assertEqual(document['x-defessential-operations'][0]['method'], 'CUSTOM')
		return

	def test_auth_schemes_with_same_kind_remain_distinct(self):
		def handler(path, credentials):
			class Secured(
				RequestRunner,
				method='GET',
				url=path,
				auth=Auth(SessionAuthorization(), credentials),
			):
				def run(self, req):
					return Response()
			return Secured

		spec = Spec('/spec')
		app = Application(exts=(spec,))
		app.register(handler('/one', Header('X-One')))
		app.register(handler('/two', Header('X-Two')))
		app.register(handler('/oauth', OAuth2Password('/token')))
		document = spec.document(app)
		schemes = document['components']['securitySchemes']
		self.assertEqual(schemes['Header']['name'], 'X-One')
		self.assertEqual(schemes['Header2']['name'], 'X-Two')
		self.assertEqual(schemes['OAuth2Password']['flows']['password']['tokenUrl'], '/token')
		return

	def test_conflicting_named_schemas_raise_instead_of_overwriting(self):
		class Conflicting(
			RequestRunner,
			method='GET',
			url='/conflict',
			response=(
				ResponseSpec(
					200,
					'정상',
					Content('application/json', Schema('Same', String())),
				),
				ResponseSpec(
					400,
					'오류',
					Content('application/json', Schema('Same', Integer())),
				),
			),
		):
			def run(self, req):
				return Response()

		spec = Spec('/spec')
		app = Application(exts=(spec,))
		app.register(Conflicting)
		with self.assertRaises(ValueError):
			spec.document(app)
		return
