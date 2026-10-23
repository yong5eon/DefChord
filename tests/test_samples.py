from http.client import HTTPConnection
from html.parser import HTMLParser
from importlib import import_module
from json import (
	dumps,
	loads,
)
from pathlib import Path
from runpy import run_path
from sys import path
from unittest import TestCase
from unittest.mock import patch

from test_server import running


SAMPLE = Path(__file__).resolve().parent.parent / 'samples'


def create_application():
	"""직접 실행하는 샘플에서 서버를 열지 않고 등록된 앱을 가져온다."""
	with patch('sys.path', [str(SAMPLE), *path]):
		with patch('DefEssential.serve') as serve:
			with patch('logging.basicConfig'):
				run_path(
					str(SAMPLE / 'Sample.py'),
					run_name='__main__',
				)
			return serve.call_args.args[2]


class RequestRunnerForms(HTMLParser):
	def __init__(self):
		super().__init__()
		self.forms = {}
		self.method = None
		return

	def handle_starttag(
		self,
		tag,
		attrs,
	):
		attributes = dict(attrs)
		if tag == 'form' and 'data-request-runner' in attributes:
			self.method = attributes['data-method']
			self.forms[self.method] = {}
		elif tag == 'input' and self.method is not None:
			self.forms[self.method][attributes['name']] = attributes['value']
		return

	def handle_endtag(
		self,
		tag,
	):
		if tag == 'form':
			self.method = None
		return


class SampleTests(TestCase):
	def test_welcome_page_and_styles_are_served(self):
		with running(create_application()) as address:
			for url, file in (
				('/', SAMPLE / 'res' / 'html' / 'welcome.html'),
				('/css/sample.css', SAMPLE / 'res' / 'css' / 'sample.css'),
			):
				status, headers, data = self.call(address, 'GET', url)
				self.assertEqual(status, 200)
				self.assertEqual(data, file.read_bytes())
			text = (SAMPLE / 'res' / 'html' / 'welcome.html').read_text(encoding='utf-8')
			for marker in (
				'id="frm-test-get"',
				'id="frm-test-post"',
				'id="frm-test-put"',
				'id="frm-test-delete"',
				'id="frm-test-2"',
				'id="btnTestStreamOut"',
				'id="btnTestChunkedStreamOut"',
				'id="btnTestServerSentEventStart"',
				'id="stream-in-command"',
				'id="chunked-stream-in-command"',
				'Transfer-Encoding: chunked',
				'/thumbs/request/sample',
				'/thumbs/response/sample',
				'bootstrap@4.6.2',
				'jquery-3.6.1.js',
			):
				self.assertIn(marker, text)
			self.assertNotIn('WebSocket', text)
			self.assertEqual(text.count(".text('curl --http1.1"), 2)
			self.assertNotIn(".text('curl.exe ", text)
		return

	def test_request_runner_form_defaults_and_validation_over_http(self):
		parser = RequestRunnerForms()
		parser.feed((SAMPLE / 'res' / 'html' / 'welcome.html').read_text(encoding='utf-8'))
		self.assertEqual(set(parser.forms), {
			'GET',
			'POST',
			'PUT',
			'DELETE',
		})
		expected = {
			'GET': 12432,
			'POST': 12995,
			'PUT': 15972,
			'DELETE': 11881,
		}
		with running(create_application()) as address:
			for method, fields in parser.forms.items():
				with self.subTest(method=method):
					url = '/api/run/{}/{}?{}'.format(
						fields['path-a'],
						fields['path-b'],
						fields['querystring'],
					)
					if method == 'GET':
						self.assertNotIn('body', fields)
					body = fields['body'].encode() if method != 'GET' else None
					headers = {'Content-Type': 'application/json'} if body is not None else {}
					status, _, data = self.call(address, method, url, body, headers)
					self.assertEqual(status, 200, data)
					value = loads(data)['data']
					self.assertEqual(value['ret'], expected[method])
					self.assertEqual(value['args']['content'], loads(body) if body is not None else None)
					for invalid_url in (
						'/api/run/100/102?a=6&b=10',
						'/api/run/101/100?a=6&b=10',
						'/api/run/101/102?a=5&b=10',
						'/api/run/101/102?a=6&b=9',
						'/api/run/101/102',
					):
						self.assertEqual(
							self.call(address, method, invalid_url, body, headers)[0],
							400,
						)
					if method != 'GET':
						for invalid_body in (
							b'{"a":5,"b":3}',
							b'{"a":2,"b":9}',
							b'{}',
							b'{',
						):
							self.assertEqual(
								self.call(address, method, url, invalid_body, headers)[0],
								400,
							)
		return

	def test_generated_handler_names(self):
		app = create_application()
		for route in app.router.routes:
			if route.url.startswith('/api/auth/') and not route.url.endswith('/token'):
				expected = 'RunAuth({})'.format(route.url.removeprefix('/api/auth/'))
				self.assertEqual(route.object.properties.name, expected)
			elif route.url.startswith('/api/content/'):
				expected = 'RunContent({})'.format(route.url.removeprefix('/api/content/'))
				self.assertEqual(route.object.properties.name, expected)
			name = route.object.properties.name
			self.assertNotIn('<locals>', name if name is not None else route.object.__qualname__)
		return

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
				('/thumbs/request/sample', 'image/jpeg'),
				('/thumbs/response/sample', 'image/png'),
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
		return

	def test_image_response_filter_replaces_jpeg_and_closes_files(self):
		app = create_application()
		response_filter = app.exts['/thumbs/response'].on_response
		original_filter = type(response_filter).__call__
		bodies = []
		requested_paths = []

		def capture(
			self,
			request,
			response,
		):
			requested_paths.append(request.params['path'])
			bodies.append(response.body)
			replacement = original_filter(self, request, response)
			bodies.append(replacement.body)
			return replacement

		with patch.object(type(response_filter), '__call__', capture):
			with running(app) as address:
				status, headers, data = self.call(address, 'GET', '/thumbs/request/sample')
				self.assertEqual(status, 200)
				self.assertEqual(headers['Content-Type'], 'image/jpeg')
				self.assertEqual(data, (SAMPLE / 'res' / 'images' / 'sample.jpg').read_bytes())
				status, headers, data = self.call(address, 'GET', '/thumbs/response/sample')
				self.assertEqual(status, 200)
				self.assertEqual(headers['Content-Type'], 'image/png')
				self.assertEqual(data, (SAMPLE / 'res' / 'images' / 'sample.png').read_bytes())
				status, headers, data = self.call(address, 'HEAD', '/thumbs/response/sample')
				self.assertEqual(status, 200)
				self.assertEqual(headers['Content-Type'], 'image/png')
				self.assertEqual(data, b'')
		self.assertEqual(requested_paths, [
			'sample.jpg',
			'sample.jpg',
		])
		self.assertEqual(len(bodies), 4)
		self.assertTrue(all(body.closed for body in bodies))
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
		app = create_application()
		with patch('runners.Streaming.sleep'):
			with running(app) as address:
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
		from DefEssential import (
			Request,
			ResponseWriter,
		)
		with patch('sys.path', [str(SAMPLE), *path]):
			RunServerSentEvent = import_module('runners.Streaming').RunServerSentEvent

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
		with patch('runners.Streaming.randrange', return_value=5):
			with patch('runners.Streaming.sleep', side_effect=ConnectionResetError):
				with self.assertRaises(ConnectionResetError):
					RunServerSentEvent().run(req)
		self.assertIn(b'data: 5\n', output.getvalue())
		self.assertIn(b'id: 5\n', output.getvalue())
		self.assertIn(b'retry: 1000\n', output.getvalue())
		return
