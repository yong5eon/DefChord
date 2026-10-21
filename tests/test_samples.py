from http.client import HTTPConnection
from importlib import import_module
from importlib.util import (
	module_from_spec,
	spec_from_file_location,
)
from json import (
	dumps,
	loads,
)
from pathlib import Path
from sys import modules
from unittest import TestCase
from unittest.mock import patch

from test_server import running


SAMPLE = Path(__file__).resolve().parent.parent / 'samples'
PACKAGE_NAME = 'defstar_http_sample'
SPEC = spec_from_file_location(
	PACKAGE_NAME,
	SAMPLE / '__init__.py',
)
if SPEC is None or SPEC.loader is None:
	raise RuntimeError('HTTP 샘플 패키지를 로드할 수 없습니다')
PACKAGE = module_from_spec(SPEC)
modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)

create_application = import_module(PACKAGE_NAME + '.Sample').create_application


class SampleTests(TestCase):
	def test_calculation_contract_has_inputs_examples_and_response_schema(self):
		app = create_application()
		document = app.exts['/api/doc'].document(app)
		operation = document['paths']['/api/run/{a}/{b}']['post']
		parameters = {
			(item['in'], item['name']): item for item in operation['parameters']
		}
		self.assertEqual(parameters['path', 'a']['schema']['exclusiveMinimum'], 100)
		self.assertEqual(parameters['query', 'b']['schema']['exclusiveMinimum'], 9)
		self.assertEqual(parameters['query', 'c']['schema']['default'], '안녕')
		content = operation['requestBody']['content']['application/json']
		self.assertEqual(content['example'], {
			'a': 2,
			'b': 3,
		})
		self.assertEqual(content['schema']['$ref'], '#/components/schemas/CalculationInput')
		self.assertEqual(
			operation['responses']['200']['content']['application/json']['schema']['$ref'],
			'#/components/schemas/CalculationResult',
		)
		schemas = document['components']['schemas']
		self.assertEqual(schemas['CalculationInput']['required'], [
			'a',
			'b',
		])
		self.assertEqual(
			schemas['CalculationResult']['properties']['data']['properties']['ret']['type'],
			'number',
		)
		return

	def call(
		self,
		address,
		method,
		url,
		body=None,
		headers=None,
		chunked=False,
	):
		connection = HTTPConnection(
			*address,
			timeout=3,
		)
		try:
			connection.request(
				method,
				url,
				body=body,
				headers=headers if headers is not None else {},
				encode_chunked=chunked,
			)
			response = connection.getresponse()
			return (
				response.status,
				dict(response.getheaders()),
				response.read(),
			)
		finally:
			connection.close()

	def test_requests_content_validation_and_files_over_http(self):
		with running(create_application()) as address:
			for method, expected in (
				('GET', 111 * 112),
				('POST', 113 * 115),
				('PUT', 121 * 132),
				('DELETE', 109 * 109),
			):
				status, headers, data = self.call(
					address,
					method,
					'/api/run/101/102?a=6&b=10',
					body=None if method == 'GET' else b'{"a":2,"b":3}',
					headers={'Content-Type': 'application/json'},
				)
				self.assertEqual(status, 200, data)
				self.assertEqual(loads(data)['data']['ret'], expected)
			for name, value, invalid in (
				('bool', True, 1),
				('integer', 1, 'x'),
				('number', 1.5, 'x'),
				('string', '문자열', 1),
				('array', [1, 2], {}),
				('object', {'a': 1}, []),
			):
				for content, expected in (
					(value, 200),
					(invalid, 400),
				):
					status, headers, data = self.call(
						address,
						'POST',
						'/api/content/' + name,
						body=dumps(content).encode(),
						headers={'Content-Type': 'application/json'},
					)
					self.assertEqual(status, expected, data)
					if status == 200:
						self.assertEqual(loads(data), content)
			status, headers, data = self.call(
				address,
				'POST',
				'/api/run/upload',
				body=b'\x00\xff',
				headers={
					'Content-Type': 'application/octet-stream',
					'Content-Format': 'application/octet-stream',
				},
			)
			self.assertEqual(status, 200, data)
			self.assertEqual(data, b'\x00\xff')
			for url, mime in (
				('/', 'text/html'),
				('/favicon.ico', None),
				('/css/sample.css', 'text/css'),
				('/thumbs/sample', 'image/jpeg'),
				('/status', None),
			):
				status, headers, data = self.call(address, 'GET', url)
				self.assertEqual(status, 200, data)
				if mime is not None:
					self.assertEqual(headers['Content-Type'], mime)
			status, headers, data = self.call(address, 'GET', '/api/doc')
			self.assertEqual(status, 200)
			self.assertEqual(loads(data)['openapi'], '3.1.0')
			status, headers, data = self.call(address, 'GET', '/swagger')
			self.assertEqual(status, 200)
			self.assertIn(b'data-spec-url="/api/doc"', data)
			self.assertEqual(self.call(address, 'GET', '/console')[0], 404)
			status, headers, data = self.call(address, 'GET', '/options?p=/status')
			self.assertEqual(status, 200)
			self.assertIn('/status', loads(data))
		return

	def test_authentication_and_tokens_over_http(self):
		with running(create_application()) as address:
			for route, query, headers in (
				('query', '?credentials=1', {}),
				('header', '', {'credentials': '1'}),
				('cookie', '', {'Cookie': 'credentials=1'}),
				('http', '', {'Authorization': 'Bearer 1'}),
				('oauth2/implicit', '', {'Authorization': 'Bearer 1'}),
				('oauth2/password', '', {'Authorization': 'Bearer 1'}),
				('oauth2/clientcredentials', '', {'Authorization': 'Bearer 1'}),
				('oauth2/authorizationcode', '', {'Authorization': 'Bearer 1'}),
			):
				url = '/api/auth/' + route
				status, response_headers, data = self.call(address, 'GET', url + query, headers=headers)
				self.assertEqual(status, 200, data)
				self.assertEqual(loads(data)['extra'], {'id': 0})
				self.assertEqual(self.call(address, 'GET', url)[0], 401)
			for flow, kind in (
				('implicit', 'token'),
				('authorizationcode', 'code'),
			):
				status, headers, data = self.call(
					address,
					'GET',
					'/api/auth/oauth2/' + flow + '/token?response_type=' + kind + '&client_id=sample',
				)
				self.assertEqual(status, 200, data)
				self.assertEqual(loads(data)['access_token'], '1')
			for flow, body in (
				('password', b'username=sample&password=example'),
				('clientcredentials', b'client_id=sample&client_secret=example'),
			):
				status, headers, data = self.call(
					address,
					'POST',
					'/api/auth/oauth2/' + flow + '/token',
					body=body,
					headers={'Content-Type': 'application/x-www-form-urlencoded'},
				)
				self.assertEqual(status, 200, data)
				self.assertEqual(loads(data)['access_token'], '1')
		return

	def test_stream_input_and_output_over_http(self):
		with patch('defstar_http_sample.Streaming.sleep'):
			with running(create_application()) as address:
				for url, chunked in (
					('/api/run/stream', False),
					('/api/run/stream/chunked', True),
				):
					status, headers, data = self.call(
						address,
						'PUT',
						url,
						body=iter((b'first', b'second')) if chunked else b'firstsecond',
						headers={'Content-Type': 'application/octet-stream'},
						chunked=chunked,
					)
					self.assertEqual(status, 200, data)
					self.assertEqual(data, b'firstsecond')
					status, headers, data = self.call(address, 'GET', url)
					self.assertEqual(status, 200, data)
					self.assertEqual(data, b'0123456789')
					if chunked:
						self.assertEqual(headers['Transfer-Encoding'], 'chunked')
		return

	def test_sse_writer_sample_contract(self):
		from io import BytesIO
		from DefStar import (
			Request,
			ResponseWriter,
		)
		RunServerSentEvent = import_module(PACKAGE_NAME + '.Streaming').RunServerSentEvent

		output = BytesIO()
		req = Request(
			'127.0.0.1',
			1,
			'GET',
			'/api/run/stream/sse',
			writer=ResponseWriter(
				lambda response, chunked: None,
				output,
			),
		)
		with patch('defstar_http_sample.Streaming.randrange', return_value=5):
			with patch('defstar_http_sample.Streaming.sleep', side_effect=ConnectionResetError):
				with self.assertRaises(ConnectionResetError):
					RunServerSentEvent().run(req)
		self.assertIn(b'data: 5\n', output.getvalue())
		self.assertIn(b'id: 5\n', output.getvalue())
		self.assertIn(b'retry: 1000\n', output.getvalue())
		return
