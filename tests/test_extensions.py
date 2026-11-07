from contextlib import redirect_stdout
from dataclasses import dataclass
from http.client import HTTPConnection
from importlib import import_module
from importlib.util import find_spec
from io import StringIO
from json import loads
from threading import Event
from typing import (
	Annotated,
	Any,
)
from unittest import (
	TestCase,
	skipUnless,
)
from unittest.mock import (
	Mock,
	patch,
)

from DefChord import (
	Application,
	ApplicationRequestResponse,
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
	ResponseSpecification,
)
from DefChord.Credentials import (
	Header,
	HTTP,
	OAuth2Password,
)
from DefChord.Descriptor import (
	Integer,
	Object,
	Properties,
	Schema,
	String,
	ToSchema,
)
from DefChord.Extensions import (
	Status,
	Ping,
	Metrics,
	Specifications,
	Swagger,
)
from DefChord.IO.Readers import (
	JavaScriptObjectNotationContentReader,
	StreamContentReader,
)
from DefChord.Runners.RunFactory import RunFactory
from DefChord.Runners.RunExtension import RunExtensionFactory
from DefChord.Validator.Patterns import ToInteger
from DefChord.IO.Writers import ChunkedStreamWriter

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
	def started(self, app):
		app.start()
		self.addCleanup(app.stop)
		return app

	def test_status_metrics_uri_and_independent_use(self):
		status = Status('/status', metrics_uri='/custom-metrics?x=1&y=2')
		app = self.started(Application(exts=(status,)))
		response = app(request('/status', headers={'Accept': 'application/json'}))
		assert isinstance(response, Response)
		assert isinstance(response.body, bytes)
		self.assertIn(b'data-metrics-uri="/custom-metrics?x=1&amp;y=2"', response.body)
		self.assertIn(b'fetch(document.body.dataset.metricsUri', response.body)
		self.assertEqual(response.header('Content-Type'), 'text/html; charset=utf-8')
		app = self.started(Application(exts=(
			Metrics('/a'),
			Metrics('/b'),
			Status('/status', metrics_uri='/b'),
		)))
		response = app(request('/status'))
		assert isinstance(response, Response)
		assert isinstance(response.body, bytes)
		self.assertIn(b'data-metrics-uri="/b"', response.body)
		return

	def test_status_invalid_metrics_uri(self):
		invalid_uris: tuple[Any, ...] = (
			None,
			'',
			'metrics',
			'https://example.com/metrics',
			'//example.com/metrics',
			'/\\example.com/metrics',
			'/metrics\n',
		)
		for uri in invalid_uris:
			with self.subTest(uri=uri):
				with self.assertRaises(ValueError):
					Status('/status', metrics_uri=uri)
		return

	def test_extension_handler_factory_contract(self):
		with self.assertRaises(TypeError):
			RunFactory()
		extension = Ping('/ping')
		app = Application(exts=(extension,))
		app.start()
		app.stop()
		factory = RunExtensionFactory(
			extension,
			'HEAD',
			'/ping',
		)
		self.assertIsInstance(factory, RunFactory)
		first = factory()
		second = factory()
		self.assertIsNot(first, second)
		self.assertTrue(issubclass(first, RequestRunner))
		self.assertEqual(first.properties.method, 'HEAD')
		self.assertEqual(first.properties.url, '/ping')
		self.assertEqual(first().run(request('/ping')).status, 503)
		return

	def test_call_is_the_required_extension_contract(self):
		class Legacy(Extension):
			def handle(self, app, request):
				return Response()

		with self.assertRaises(TypeError):
			Legacy()
		extension = Ping('/ping')
		self.assertTrue(callable(extension))
		self.assertFalse(hasattr(extension, 'handle'))
		return

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
		collector = metrics.collector
		spec = Specifications('/spec')
		app = Application(
			exts=(
				Status('/status', metrics_uri='/metrics', title='<DefChord>'),
				Swagger('/swagger', spec_uri='/spec'),
				metrics,
				spec,
				Ping('/ping'),
			),
		)
		app.add(Echo)
		other = Application(exts=(Specifications('/spec'),))
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
				status, headers, body = self.get(address, '/metrics', {'Accept': 'application/json'})
				self.assertEqual(status, 200)
				self.assertTrue(headers['Content-Type'].startswith('application/json'))
				self.assertEqual(headers['Cache-Control'], 'no-store')
				self.assertIn('GET /echo/:id', loads(body)['requests'])
				status, headers, body = self.get(address, '/swagger')
				self.assertIn(b'data-spec-url="/spec"', body)
				self.assertIn(b'SwaggerUIBundle', body)
				status, headers, body = self.get(address, '/status')
				self.assertIn(b'&lt;DefChord&gt;', body)
				self.assertIn(b'<title>&lt;DefChord&gt; Status</title>', body)
				self.assertIn(b'data-metrics-uri="/metrics"', body)
				self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
				status, headers, body = self.get(address, '/ping')
				self.assertEqual(status, 200)
				self.assertEqual(loads(body), {'status': 'running'})
		self.assertFalse(app.running)
		self.assertIn('Extensions: 5 extensions', output.getvalue())
		self.assertIn(
			'  Extensions: 5 extensions\n' + '\n'.join(
				'    - ' + str(extension) for extension in app.exts
			),
			output.getvalue(),
		)
		self.assertNotIn(f'Swagger: http://127.0.0.1:{address[1]}', output.getvalue())
		self.started(other)
		other_spec = next(extension for extension in other.exts if isinstance(extension, Specifications))
		self.assertEqual(other_spec.document()['paths'], {})
		specification = next(extension for extension in app.exts if isinstance(extension, Specifications))
		self.assertNotIn('/spec', specification.document()['paths'])
		self.assertNotIn('/status', specification.document()['paths'])
		ping_extension = Ping('/state')
		state = Application(exts=(ping_extension,))
		state.start()
		state.stop()
		ping = ping_extension(request())
		assert isinstance(ping.body, bytes)
		self.assertEqual(ping.status, 503)
		self.assertEqual(loads(ping.body)['status'], 'stopped')
		return

	def test_dependency_collision_and_instance_ownership(self):
		for extensions in (
			(Specifications('/same'), Specifications('/same')),
		):
			with self.assertRaises(ValueError):
				Application(exts=extensions).start()
		extension = Ping('/ping')
		app = Application(exts=(extension,))
		self.assertEqual(app.exts, (extension,))
		with self.assertRaises(ValueError):
			Application(exts=(extension,))
		self.started(app)

		class Conflict(
			RequestRunner,
			method='GET',
			url='/metrics',
		):
			def run(self, req):
				return Response()

		app = Application(exts=(Specifications('/metrics'),))
		app.add(Conflict)
		with self.assertRaises(ValueError):
			app.start()
		with self.assertRaises(ValueError):
			Specifications('/:variable')
		return

	def test_lifecycle_order_rollback_and_failures_are_explicit(self):
		events = []

		class Lifecycle(Extension):
			def __init__(self, path, fail=False):
				super().__init__()
				self.path = path
				self.fail = fail
				return

			def startup(self, app):
				if self.fail:
					raise ValueError('시작 실패')
				events.append('start:' + self.path)
				super().startup(app)
				return

			def cleanup(self):
				events.append('stop:' + self.path)
				super().cleanup()
				return

			def __call__(self, req):
				return Response()

		app = Application(exts=(
			Lifecycle('/first'),
			Lifecycle('/last'),
		))
		app.start()
		with self.assertRaises(RuntimeError):
			app.start()
		with self.assertRaises(RuntimeError):
			app.add(Echo)
		app.stop()
		app.stop()
		self.assertEqual(events, ['start:/first', 'start:/last', 'stop:/last', 'stop:/first'])
		events.clear()
		app = Application(exts=(
			Lifecycle('/first'),
			Lifecycle('/fail', fail=True),
		))
		with self.assertRaises(ValueError):
			app.start()
		self.assertFalse(app.running)
		self.assertEqual(events, ['start:/first', 'stop:/first'])
		return

	def test_swagger_spec_uri_escaping_headers_and_head(self):
		swagger = Swagger('/swagger', spec_uri='/custom-spec', title='<DefChord>', description='</script>')
		spec = Specifications('/custom-spec')
		app = self.started(Application(exts=(
			swagger,
			spec,
		)))
		response = app(request('/swagger'))
		assert isinstance(response, Response)
		assert isinstance(response.body, bytes)
		self.assertIn(b'data-spec-url="/custom-spec"', response.body)
		self.assertIn(b'&lt;DefChord&gt;', response.body)
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
		self.assertIn("img-src 'self' data: blob:", policy)
		self.assertIn('https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/', policy)
		specification = next(extension for extension in app.exts if isinstance(extension, Specifications))
		self.assertNotIn('/swagger', specification.document()['paths'])
		response = app(request('/swagger', headers={'Accept': 'application/json'}))
		assert isinstance(response, Response)
		content_type = response.header('Content-Type')
		assert isinstance(content_type, str)
		self.assertTrue(content_type.startswith('text/html'))
		app.stop()
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

	def test_swagger_invalid_settings_and_independent_use(self):
		invalid_settings: tuple[dict[str, Any], ...] = (
			{'title': ''},
			{'title': None},
			{'description': None},
		)
		for settings in invalid_settings:
			with self.subTest(settings=settings):
				with self.assertRaises(ValueError):
					Swagger('/swagger', spec_uri='/spec', **settings)
		for uri in (
			None,
			'',
			'spec.json',
			'https://example.com/spec',
			'//example.com/spec',
			'/\\example.com/spec',
			'/spec\n',
		):
			with self.subTest(uri=uri):
				with self.assertRaises(ValueError):
					Swagger('/swagger', spec_uri=uri)
		swagger = Swagger('/swagger', spec_uri='/external-spec?format=json&version=1')
		response = swagger(request('/swagger'))
		assert isinstance(response.body, bytes)
		self.assertIn(b'data-spec-url="/external-spec?format=json&amp;version=1"', response.body)
		app = self.started(Application(exts=(
			Specifications('/a'),
			Specifications('/b'),
			Swagger('/swagger', spec_uri='/b'),
		)))
		response = app(request('/swagger'))
		assert isinstance(response, Response)
		assert isinstance(response.body, bytes)
		self.assertIn(b'data-spec-url="/b"', response.body)
		return

	def test_metrics_windows_and_unmatched_cardinality(self):
		metrics_module = import_module('DefChord.Extensions.Metrics')
		extension = Metrics('/metrics')
		metrics = extension.collector
		app = Application(exts=(extension,))
		app.add(Echo)
		with patch.object(metrics_module, 'monotonic', return_value=100.0):
			app.start()
			req = request('/echo/one')
			metrics.begin(req)
			self.assertEqual(metrics.snapshot()['requests']['GET /echo/:id']['active'], 1)
		with patch.object(metrics_module, 'monotonic', return_value=102.0):
			metrics.end(req, 200, None)
		with patch.object(metrics_module, 'monotonic', return_value=103.0):
			stats = metrics.snapshot()['requests']['GET /echo/:id']
			self.assertEqual(stats['windows']['1']['success'], 1)
			self.assertEqual(stats['windows']['1']['max_duration'], 2.0)
			self.assertEqual(stats['duration'], 2.0)
		for uri in (
			'/unknown-one',
			'/unknown-two',
		):
			req = request(uri)
			metrics.begin(req)
			metrics.end(req, 404, None)
		self.assertEqual(metrics.snapshot()['requests']['<unmatched>']['failure'], 2)
		self.assertNotIn('/unknown-one', metrics.requests)
		rendered = metrics.render()
		self.assertIn('route="GET /echo/:id"', rendered)
		self.assertIn('# HELP defchord_requests_total', rendered)
		app.stop()
		return

	def test_metrics_stream_completes_at_application_return_and_observes_processing_error(self):
		release = Event()
		extension = Metrics('/metrics')
		metrics = extension.collector

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

		app = Application(
			exts=(extension,),
		)
		app.add(Stream)
		app.add(Invalid)
		with redirect_stdout(StringIO()):
			with running(app) as address:
				connection = HTTPConnection(*address, timeout=3)
				try:
					connection.request('GET', '/stream')
					response = connection.getresponse()
					self.assertEqual(response.read(5), b'first')
					self.assertEqual(metrics.snapshot()['requests']['GET /stream']['active'], 0)
					release.set()
					self.assertEqual(response.read(), b'last')
					self.assertEqual(metrics.snapshot()['requests']['GET /stream']['success'], 1)
					self.assertEqual(self.get(address, '/error')[0], 400)
					self.assertEqual(metrics.snapshot()['requests']['GET /error']['failure'], 1)
				finally:
					release.set()
					connection.close()
		return

	def test_metrics_direct_output_status_and_failed_stream(self):
		done = Event()

		class Completion(ApplicationRequestResponse):
			def __call__(self, req, response):
				done.set()
				return response

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

		extension = Metrics('/metrics')
		metrics = extension.collector
		app = Application(
			exts=(extension,),
			on_request_response=Completion(),
		)
		app.add(Direct)
		with redirect_stdout(StringIO()):
			with running(app) as address:
				self.assertEqual(self.get(address, '/direct')[0], 400)
				self.assertTrue(done.wait(3))
				self.assertEqual(metrics.snapshot()['requests']['GET /direct']['failure'], 1)
		return

	def test_metrics_does_not_reclassify_later_stream_failure(self):
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

		extension = Metrics('/metrics')
		metrics = extension.collector
		app = Application(
			exts=(extension,),
		)
		app.add(Broken)
		with redirect_stdout(StringIO()):
			with self.assertLogs('Server', level='ERROR'):
				with running(app) as address:
					self.assertEqual(self.get(address, '/broken')[2], b'partial')
					stats = metrics.snapshot()['requests']['GET /broken']
					self.assertEqual(stats['failure'], 0)
					self.assertEqual(stats['success'], 1)
					self.assertEqual(stats['active'], 0)
		return


class SpecTests(TestCase):
	def test_specifications_default_json_output_is_preserved(self):
		app = Application(exts=(Specifications('/spec'),))
		app.start()
		self.addCleanup(app.stop)
		response = app(request('/spec'))
		assert isinstance(response, Response)
		content_type = response.header('Content-Type')
		assert isinstance(content_type, str)
		self.assertTrue(content_type.startswith('application/json'))
		assert isinstance(response.body, bytes)
		self.assertEqual(loads(response.body)['openapi'], '3.1.0')
		return

	@skipUnless(find_spec('yaml') is not None, 'PyYAML 선택적 의존성 필요')
	def test_specifications_yaml_output_matches_json_semantics(self):
		yaml = import_module('yaml')

		class Documented(
			RequestRunner,
			method='POST',
			url='/items/:id',
			body=Body(
				JavaScriptObjectNotationContentReader(),
				content=Content(
					'application/json',
					Schema('Input', Object(properties=Properties(
						value=Integer(min=0),
					))),
					{
						'message': '안녕',
						'truthy': 'true',
						'nullish': 'null',
						'numberish': '0123',
						'key:true': 'value',
					},
				),
			),
			response=ResponseSpecification(
				200,
				'ok',
				Content(
					'application/json',
					Schema('Output', Object(properties=Properties(
						result=String(),
					))),
				),
			),
			auth=Auth(
				SessionAuthorization(),
				HTTP('Bearer'),
			),
		):
			def run(self, req):
				return Response()

		class Custom(
			RequestRunner,
			method='CUSTOM',
			url='/custom',
		):
			def run(self, req):
				return Response()

		app = Application(exts=(
			Specifications('/spec-json'),
			Specifications('/spec-yaml', document_format='yaml'),
		))
		app.add(Documented)
		app.add(Custom)
		app.start()
		self.addCleanup(app.stop)
		json_response = app(request('/spec-json'))
		yaml_response = app(request('/spec-yaml'))
		assert isinstance(json_response, Response)
		assert isinstance(yaml_response, Response)
		yaml_content_type = yaml_response.header('Content-Type')
		assert isinstance(yaml_content_type, str)
		self.assertTrue(yaml_content_type.startswith('application/yaml; charset=utf-8'))
		assert isinstance(yaml_response.body, bytes)
		self.assertIn('안녕'.encode('utf-8'), yaml_response.body)
		json_document = loads(json_response.body)
		yaml_document = yaml.safe_load(yaml_response.body.decode('utf-8'))
		self.assertEqual(json_document, yaml_document)
		self.assertIn('/items/{id}', yaml_document['paths'])
		self.assertIn('Input', yaml_document['components']['schemas'])
		self.assertEqual(
			yaml_document['paths']['/items/{id}']['post']['requestBody']['content']['application/json']['schema']['$ref'],
			'#/components/schemas/Input',
		)
		self.assertEqual(yaml_document['components']['securitySchemes']['HTTP']['scheme'], 'bearer')
		self.assertIn('x-defchord-operations', yaml_document)
		example = yaml_document['paths']['/items/{id}']['post']['requestBody']['content']['application/json']['example']
		self.assertEqual(example['truthy'], 'true')
		self.assertEqual(example['nullish'], 'null')
		self.assertEqual(example['numberish'], '0123')
		self.assertEqual(example['key:true'], 'value')
		return

	def test_specifications_rejects_unsupported_document_format(self):
		with self.assertRaises(ValueError):
			Specifications('/spec', document_format='xml')
		return

	def test_specifications_yaml_requires_dependency_without_silent_fallback(self):
		app = Application(exts=(
			Specifications('/spec', document_format='yaml'),
		))
		app.start()
		self.addCleanup(app.stop)
		with patch(
			'DefChord.Extensions.Specifications.import_module',
			side_effect=ModuleNotFoundError('No module named yaml'),
		):
			with self.assertRaisesRegex(ModuleNotFoundError, 'YAML output requires PyYAML'):
				app(request('/spec'))
		return

	def test_specifications_yaml_serialization_failure_is_propagated(self):
		app = Application(exts=(
			Specifications('/spec', document_format='yaml'),
		))
		app.start()
		self.addCleanup(app.stop)
		serializer = Mock()
		serializer.safe_dump.side_effect = TypeError('yaml dump failed')
		with patch(
			'DefChord.Extensions.Specifications.import_module',
			return_value=serializer,
		):
			with self.assertRaisesRegex(TypeError, 'yaml dump failed'):
				app(request('/spec'))
		return

	def test_live_extension_ownership_does_not_hide_general_methods_at_same_path(self):
		class Submit(
			RequestRunner,
			method='POST',
			url='/shared',
		):
			def run(
				self,
				req,
			):
				return Response()

		app = Application(exts=(
			Specifications('/spec'),
			Ping('/shared'),
		))
		app.add(Submit)
		app.start()
		self.addCleanup(app.stop)
		specification = next(extension for extension in app.exts if isinstance(extension, Specifications))
		document = specification.document()
		self.assertEqual(set(document['paths']['/shared']), {'post'})
		self.assertNotIn('/spec', document['paths'])
		return

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
			response=ResponseSpecification(
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

		class Upload(
			RequestRunner,
			method='PUT',
			url='/upload',
			body=Body(StreamContentReader()),
		):
			def run(self, req):
				return Response()

		specification = Specifications('/spec')
		app = Application(exts=(specification,))
		app.add(Documented)
		app.add(Custom)
		app.add(Upload)
		app.start()
		self.addCleanup(app.stop)
		spec = next(extension for extension in app.exts if isinstance(extension, Specifications))
		document = spec.document()
		self.assertEqual(
			list(document['paths']['/upload']['put']['requestBody']['content']),
			['*/*'],
		)
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
		self.assertEqual(document['x-defchord-operations'][0]['method'], 'CUSTOM')
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

		app = Application(exts=(Specifications('/spec'),))
		app.add(handler('/one', Header('X-One')))
		app.add(handler('/two', Header('X-Two')))
		app.add(handler('/oauth', OAuth2Password('/token')))
		app.start()
		self.addCleanup(app.stop)
		spec = next(extension for extension in app.exts if isinstance(extension, Specifications))
		document = spec.document()
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
				ResponseSpecification(
					200,
					'정상',
					Content('application/json', Schema('Same', String())),
				),
				ResponseSpecification(
					400,
					'오류',
					Content('application/json', Schema('Same', Integer())),
				),
			),
		):
			def run(self, req):
				return Response()

		app = Application(exts=(Specifications('/spec'),))
		app.add(Conflicting)
		app.start()
		self.addCleanup(app.stop)
		spec = next(extension for extension in app.exts if isinstance(extension, Specifications))
		with self.assertRaises(ValueError):
			spec.document()
		return
