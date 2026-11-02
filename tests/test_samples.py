from http.client import HTTPConnection
from html.parser import HTMLParser
from importlib import import_module
from io import BytesIO
from json import (
	dumps,
	loads,
)
from logging import getLogger
from pathlib import Path
from runpy import run_path
from struct import pack
from sys import path
from unittest import TestCase
from unittest.mock import patch
from DefChord import (
	Request,
	RequestReader,
	ResponseWriter,
)
from DefChord.Extensions import Specifications

from test_server import running


SAMPLE = Path(__file__).resolve().parent.parent / 'samples'


def create_application():
	"""Load the application registered by the directly executed sample without starting a server."""
	with patch('sys.path', [str(SAMPLE), *path]):
		with patch('DefChord.Adapter.Implements.Python.Server') as server:
			run_path(
				str(SAMPLE / 'Sample.py'),
				run_name='__main__',
			)
			return server.call_args.args[2]


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
	def setUp(self):
		root = getLogger()
		self.logging_handlers = root.handlers[:]
		self.logging_level = root.level
		self.addCleanup(self.restore_logging)
		return

	def restore_logging(self):
		root = getLogger()
		for handler in root.handlers[:]:
			if handler not in self.logging_handlers:
				root.removeHandler(handler)
				handler.close()
		root.setLevel(self.logging_level)
		return

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
				'id="btnTestWebSocketStart"',
				"'/api/run/ws', 'echo'",
				'id="stream-in-command"',
				'id="chunked-stream-in-command"',
				'Transfer-Encoding: chunked',
				'/thumbs/request/sample',
				'/thumbs/response/sample',
				'bootstrap@4.6.2',
				'jquery-3.6.1.js',
			):
				self.assertIn(marker, text)
			self.assertEqual(text.count(".text('curl --http1.1"), 2)
			self.assertNotIn(".text('curl.exe ", text)
		return

	def test_request_runner_error_hook_returns_custom_sample_response(self):
		with running(create_application()) as address:
			status, headers, data = self.call(address, 'GET', '/api/run/error')
		self.assertEqual(status, 418)
		self.assertEqual(data, b'Handled by RequestRunner error hook.')
		self.assertEqual(headers['Content-Type'], 'text/plain; charset=utf-8')
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
		app.start()
		self.addCleanup(app.stop)
		specifications = next(extension for extension in app.exts if isinstance(extension, Specifications))
		document = specifications.document()
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
		self.assertEqual(
			document['paths']['/api/run/upload']['post']['requestBody']['content'],
			{'application/octet-stream': {'schema': {
				'type': 'string',
				'format': 'binary',
			}}},
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
		extension = next(
			extension for extension in app.exts
			if getattr(extension, 'path', None) == '/thumbs/response'
		)
		response_filter, = extension.request_response_hooks
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
		with patch('samples.runners.Streaming.sleep'):
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
				# Do not send a body for requests rejected by headers, avoiding a race with the early response.
				status, headers, data = self.call(
					address,
					'PUT',
					'/api/run/stream/chunked',
					headers={
						'Content-Type': 'application/octet-stream',
						'Content-Length': '11',
					},
				)
				self.assertEqual(status, 400, data)
				self.assertEqual(data, b'Chunked transfer encoding is required')
				self.assertEqual(headers['Connection'], 'close')
				status, headers, data = self.call(
					address,
					'PUT',
					'/api/run/stream',
					headers={
						'Content-Type': 'application/octet-stream',
						'Transfer-Encoding': 'chunked',
					},
				)
				self.assertEqual(status, 411, data)
				self.assertEqual(data, b'Content-Length is required')
				self.assertEqual(headers['Connection'], 'close')
		return

	def test_streaming_request_and_response_hook_logs_before_headers(self):
		app = create_application()
		streaming = import_module('samples.runners.Streaming')
		for method, uri, mode in (
			('PUT', '/api/run/stream', 'input'),
			('PUT', '/api/run/stream/chunked', 'chunked-input'),
			('GET', '/api/run/stream', 'output'),
			('GET', '/api/run/stream/chunked', 'chunked-output'),
			('GET', '/api/run/stream/sse', 'sse'),
			('GET', '/api/run/ws', 'websocket'),
		):
			with self.subTest(mode=mode):
				output = BytesIO()
				sent = []
				headers = {}
				if method == 'PUT':
					headers['Content-Type'] = 'application/octet-stream'
				if mode == 'websocket':
					headers.update({
						'Upgrade': 'websocket',
						'Connection': 'Upgrade',
						'Sec-WebSocket-Version': '13',
						'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
					})
				reader = RequestReader(
					BytesIO(b'3\r\nabc\r\n0\r\n\r\n' if mode == 'chunked-input' else b'abc'),
					size=None if mode == 'chunked-input' else (3 if method == 'PUT' else 0),
					chunked=mode == 'chunked-input',
				)
				with self.assertLogs('Sample.Streaming', level='DEBUG') as logs:
					def send(
						response,
						chunked,
					):
						self.assertEqual(len(logs.records), 2)
						self.assertEqual(output.getvalue(), b'')
						self.assertEqual(response.header('X-Request-ID'), req.id)
						sent.append(response.status)
						return

					writer = ResponseWriter(
						send,
						output,
					)
					req = Request(
						'127.0.0.1',
						1,
						method,
						uri,
						headers=headers,
						reader=reader,
						writer=writer,
					)
					with patch.object(streaming, 'sleep', side_effect=ConnectionResetError if mode == 'sse' else None):
						with patch.object(streaming, 'randrange', return_value=5):
							with patch.object(streaming.WebSocket, 'receive', return_value=None):
								if mode == 'sse':
									with self.assertRaises(ConnectionResetError):
										app(req)
								else:
									self.assertIsNone(app(req))
				self.assertEqual(len(logs.records), 3 if mode == 'sse' else 2)
				self.assertEqual(logs.records[0].getMessage(), (
					'요청 훅: id={} (핸들러 실행 전)'.format(req.id)
				))
				status = 101 if mode == 'websocket' else 200
				self.assertEqual(logs.records[1].getMessage(), (
					'응답 훅: id={} status={} (헤더 전송 전)'.format(
						req.id,
						status,
					)
				))
				self.assertEqual(sent, [status])
				if mode == 'sse':
					self.assertEqual(logs.records[2].levelname, 'DEBUG')
					self.assertIn('오류 훅: id=' + req.id, logs.records[2].getMessage())
					self.assertIsNone(logs.records[2].exc_info)
					self.assertIn('error_type=ConnectionResetError', logs.records[2].getMessage())
				self.assertIsNone(writer.on_request_response)
				if mode == 'sse':
					self.assertIn(b'data: 5\n', output.getvalue())
				elif method == 'PUT':
					self.assertIn(b'abc', output.getvalue())
				elif mode != 'websocket':
					self.assertIn(b'0', output.getvalue())
		return

	def test_request_sample_hooks_log_normal_and_error_paths(self):
		app = create_application()
		requests = import_module('samples.runners.Requests')
		for runner in (
			requests.RunGet,
			requests.RunPost,
			requests.RunPut,
			requests.RunDelete,
			requests.RunUpload,
		):
			with self.subTest(runner=runner.__name__):
				method = runner.properties.method
				upload = runner is requests.RunUpload
				uri = '/api/run/upload' if upload else '/api/run/101/102?a=6&b=10'
				body = b'abc' if upload else (b'' if method == 'GET' else b'{"a":2,"b":3}')
				headers = {
					'Content-Type': 'application/octet-stream' if upload else 'application/json',
				}
				if upload:
					headers['Content-Format'] = 'application/octet-stream'

				def make_request():
					return Request(
						'127.0.0.1',
						1,
						method,
						uri,
						headers=headers,
						reader=RequestReader(
							BytesIO(body),
							size=len(body),
						),
					)

				req = make_request()
				with self.assertLogs('Sample.Requests', level='DEBUG') as logs:
					response = app(req)
				self.assertEqual(response.status, 200)
				self.assertEqual(len(logs.records), 2)
				self.assertTrue(logs.records[0].getMessage().startswith('요청 훅: id=' + req.id))
				self.assertTrue(logs.records[1].getMessage().startswith('응답 훅: id=' + req.id))
				response.close()

				req = make_request()
				error = ValueError('샘플 오류 훅 검증')
				with patch.object(runner, 'run', side_effect=error):
					with self.assertLogs('Sample.Requests', level='DEBUG') as logs:
						with self.assertRaises(ValueError) as caught:
							app(req)
				self.assertIs(caught.exception, error)
				self.assertEqual(len(logs.records), 2)
				self.assertTrue(logs.records[0].getMessage().startswith('요청 훅: id=' + req.id))
				self.assertTrue(logs.records[1].getMessage().startswith('오류 훅: id=' + req.id))
				self.assertIsNone(logs.records[1].exc_info)
				self.assertIn('error_type=ValueError', logs.records[1].getMessage())
		return

	def test_streaming_error_hooks_are_connected_for_all_handlers(self):
		app = create_application()
		streaming = import_module('samples.runners.Streaming')
		for runner in (
			streaming.RunStreamIn,
			streaming.RunChunkedStreamIn,
			streaming.RunStreamOut,
			streaming.RunChunkedStreamOut,
			streaming.RunServerSentEvent,
			streaming.RunWebSocket,
		):
			with self.subTest(runner=runner.__name__):
				chunked = runner is streaming.RunChunkedStreamIn
				error = ValueError('스트리밍 오류 훅 검증')
				req = Request(
					'127.0.0.1',
					1,
					runner.properties.method,
					runner.properties.url,
					headers={'Content-Type': 'application/octet-stream'},
					reader=RequestReader(
						BytesIO(b'0\r\n\r\n' if chunked else b'abc'),
						size=None if chunked else (3 if runner is streaming.RunStreamIn else 0),
						chunked=chunked,
					),
				)
				with patch.object(runner, 'run', side_effect=error):
					with self.assertLogs('Sample.Streaming', level='DEBUG') as logs:
						with self.assertRaises(ValueError) as caught:
							app(req)
				self.assertIs(caught.exception, error)
				self.assertEqual(len(logs.records), 2)
				self.assertTrue(logs.records[0].getMessage().startswith('요청 훅: id=' + req.id))
				self.assertTrue(logs.records[1].getMessage().startswith('오류 훅: id=' + req.id))
				self.assertIsNone(logs.records[1].exc_info)
				self.assertIn('error_type=ValueError', logs.records[1].getMessage())
		return

	def test_sse_writer_sample_contract(self):
		from io import BytesIO
		from DefChord import (
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

	def test_websocket_echo_sample_over_http(self):
		from test_websocket import (
			Client,
			client_frame,
		)
		from DefChord.IO.WebSocket import WebSocketFrame
		with running(create_application()) as address:
			client = Client(
				address,
				{'Sec-WebSocket-Protocol': 'echo'},
				'/api/run/ws',
			)
			try:
				self.assertEqual(client.status, 101)
				self.assertEqual(client.headers['sec-websocket-protocol'], 'echo')
				client.send(client_frame(WebSocketFrame.TEXT, '안녕'.encode('utf-8')))
				self.assertEqual(client.receive(), (WebSocketFrame.TEXT, True, '안녕'.encode('utf-8')))
				client.send(client_frame(WebSocketFrame.BINARY, b'\x00\x01'))
				self.assertEqual(client.receive(), (WebSocketFrame.BINARY, True, b'\x00\x01'))
				client.send(client_frame(WebSocketFrame.CLOSE, pack('!H', 1000)))
				self.assertEqual(client.receive(), (WebSocketFrame.CLOSE, True, pack('!H', 1000)))
			finally:
				client.close()
		return
