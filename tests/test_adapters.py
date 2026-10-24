from contextlib import (
	nullcontext,
	redirect_stdout,
)
from http.client import HTTPConnection
from importlib.util import find_spec
from inspect import isabstract
from io import (
	BytesIO,
	StringIO,
)
from os import name
from pathlib import Path
from socket import socket
from subprocess import (
	Popen,
	TimeoutExpired,
)
from sys import executable
from tempfile import TemporaryDirectory
from threading import (
	Event,
	Thread,
)
from time import (
	monotonic,
	sleep,
)
from unittest import (
	TestCase,
	skipUnless,
)
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

from DefEssential import (
	Application,
	Body,
	Extension,
	RequestRunner,
	Response,
)
from DefEssential.Adapter import Server as ServerAdapter
from DefEssential.Adapter.Implements.Gunicorn import Server as GunicornServer
from DefEssential.Adapter.Implements.Python import Server as PythonServer
from DefEssential.Adapter.Implements.Uvicorn import Server as UvicornServer
from DefEssential.Adapter.WSGI import WSGIApplication
from DefEssential.IO.Readers import (
	ChunkedStreamContentReader,
	StreamContentReader,
)


class Lifecycle(Extension):
	def __init__(self):
		super().__init__('/lifecycle')
		self.events = []
		return

	def start(
		self,
		application,
	):
		self.events.append('start')
		return

	def stop(
		self,
		application,
	):
		self.events.append('stop')
		return

	def __call__(
		self,
		application,
		request,
	):
		return Response()


class AdapterTests(TestCase):
	def test_python_supports_three_call_styles(self):
		for style in (
			'assigned',
			'inline',
			'context',
		):
			with self.subTest(style=style):
				lifecycle = Lifecycle()
				application = Application(exts=(lifecycle,))
				with redirect_stdout(StringIO()):
					with patch('http.server.ThreadingHTTPServer.serve_forever', side_effect=KeyboardInterrupt):
						if style == 'assigned':
							server = PythonServer('127.0.0.1', 0, application)
							server.run()
							self.assertEqual(server.socket.fileno(), -1)
						elif style == 'inline':
							PythonServer('127.0.0.1', 0, application).run()
						else:
							with PythonServer('127.0.0.1', 0, application) as server:
								server.run()
							self.assertEqual(server.socket.fileno(), -1)
				self.assertEqual(lifecycle.events, [
					'start',
					'stop',
				])
				self.assertFalse(application.running)
		return

	def test_context_without_run_does_not_start_application_or_hide_errors(self):
		for implementation in (
			PythonServer,
			GunicornServer,
			UvicornServer,
		):
			for failed in (
				False,
				True,
			):
				with self.subTest(implementation=implementation, failed=failed):
					lifecycle = Lifecycle()
					application = Application(exts=(lifecycle,))
					server = implementation('127.0.0.1', 0, application)
					expected = self.assertRaisesRegex(RuntimeError, 'body failed') if failed else nullcontext()
					with expected:
						with server as entered:
							self.assertIs(entered, server)
							self.assertEqual(lifecycle.events, [])
							if failed:
								raise RuntimeError('body failed')
					self.assertEqual(lifecycle.events, [])
					self.assertFalse(application.running)
					if isinstance(server, PythonServer):
						self.assertEqual(server.socket.fileno(), -1)
		return

	def test_common_interface_and_python_run_cleanup(self):
		self.assertTrue(isabstract(ServerAdapter))
		lifecycle = Lifecycle()
		application = Application(exts=(lifecycle,))
		server = PythonServer(
			'127.0.0.1',
			0,
			application,
		)
		self.assertIsInstance(server, ServerAdapter)
		with redirect_stdout(StringIO()):
			with patch('http.server.ThreadingHTTPServer.serve_forever', side_effect=KeyboardInterrupt):
				server.run()
		self.assertEqual(lifecycle.events, [
			'start',
			'stop',
		])
		self.assertFalse(application.running)
		self.assertEqual(server.socket.fileno(), -1)
		for implementation in (
			GunicornServer,
			UvicornServer,
		):
			self.assertIsInstance(implementation('127.0.0.1', 0, Application()), ServerAdapter)
		return

	def test_python_run_closes_socket_after_startup_failure(self):
		application = Application()
		server = PythonServer('127.0.0.1', 0, application)
		with patch.object(application, 'start', side_effect=RuntimeError('startup failed')):
			with self.assertRaisesRegex(RuntimeError, 'startup failed'):
				server.run()
		self.assertEqual(server.socket.fileno(), -1)
		return

	def test_invalid_configuration(self):
		with self.assertRaises(ValueError):
			GunicornServer('127.0.0.1', 8000, Application(), workers=0)
		with self.assertRaises(ValueError):
			GunicornServer('127.0.0.1', 8000, Application(), bind=':9000')
		for create in (
			lambda: UvicornServer('127.0.0.1', 8000, Application(), workers=2),
			lambda: UvicornServer('127.0.0.1', 8000, Application(), reload=True),
			lambda: UvicornServer('127.0.0.1', 8000, Application(), wsgi_workers=0),
			lambda: UvicornServer('127.0.0.1', 8000, Application(), send_queue_size=0),
			lambda: UvicornServer('127.0.0.1', 8000, Application(), interface='wsgi'),
			lambda: UvicornServer('127.0.0.1', 8000, Application(), ws='none'),
			lambda: UvicornServer('127.0.0.1', 8000, Application(), ws_max_size=1024),
		):
			self.assertRaises(
				ValueError,
				create,
			)
		return

	@skipUnless(name == 'nt', 'Windows 전용 플랫폼 오류 검증')
	def test_gunicorn_reports_unsupported_platform(self):
		with self.assertRaisesRegex(RuntimeError, 'POSIX'):
			GunicornServer('127.0.0.1', 8000, Application()).run()
		return


class WSGITests(TestCase):
	def invoke(
		self,
		application,
		**values,
	):
		environ = {}
		setup_testing_defaults(environ)
		environ.update(values)
		result = {
			'status': None,
			'headers': [],
			'body': [],
		}

		def start_response(
			status,
			headers,
		):
			result['status'] = status
			result['headers'] = headers
			return result['body'].append

		iterable = WSGIApplication(application)(environ, start_response)
		result['body'].extend(iterable)
		result['body'] = b''.join(result['body'])
		return result

	def test_custom_method_uri_and_empty_gunicorn_input(self):
		class Sample(
			RequestRunner,
			method='CUSTOM',
			url='/sample/:id',
		):
			def run(
				self,
				request,
			):
				return Response(body=f'{request.params["id"]}:{request.args["x"]}'.encode())

		application = Application()
		application.add(Sample)
		result = self.invoke(
			application,
			REQUEST_METHOD='CUSTOM',
			PATH_INFO='/sample/42',
			QUERY_STRING='x=hello',
			**{'wsgi.input_terminated': True},
		)
		self.assertEqual(result['status'], '200 OK')
		self.assertEqual(result['body'], b'42:hello')
		encoded = self.invoke(
			application,
			REQUEST_METHOD='CUSTOM',
			PATH_INFO='/sample/a/b',
			QUERY_STRING='x=hello',
			**{'asgi.scope': {'raw_path': b'/sample/a%2Fb'}},
		)
		self.assertEqual(encoded['body'], b'a%2Fb:hello')
		return

	def test_known_length_and_server_decoded_chunked_uploads(self):
		for chunked in (
			False,
			True,
		):
			with self.subTest(chunked=chunked):
				class Upload(
					RequestRunner,
					method='POST',
					url='/',
					body=Body(ChunkedStreamContentReader() if chunked else StreamContentReader()),
				):
					def run(
						self,
						request,
					):
						first = request.body.chunk(2) if chunked else request.body.read(2)
						return Response(body=first + request.body.read())

				application = Application()
				application.add(Upload)
				values = {
					'REQUEST_METHOD': 'POST',
					'CONTENT_TYPE': 'application/octet-stream',
					'wsgi.input': BytesIO(b'abcdef'),
				}
				if chunked:
					values['HTTP_TRANSFER_ENCODING'] = 'chunked'
				else:
					values['CONTENT_LENGTH'] = '6'
				result = self.invoke(application, **values)
				self.assertEqual(result['status'], '200 OK')
				self.assertEqual(result['body'], b'abcdef')
		return

	def test_direct_chunked_stream_is_not_double_framed(self):
		class Stream(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				request.writer.begin(Response(), chunked=True)
				request.writer.write(b'abc')
				request.writer.flush()
				request.writer.write(b'def')
				request.writer.end()
				return

		application = Application()
		application.add(Stream)
		result = self.invoke(application)
		self.assertEqual(result['body'], b'abcdef')
		self.assertNotIn('Transfer-Encoding', dict(result['headers']))
		return

	def test_error_head_no_body_and_upgrade(self):
		class Sample(
			RequestRunner,
			method='HEAD',
			url='/',
		):
			def run(
				self,
				request,
			):
				return Response(body=b'hello')

		application = Application()
		application.add(Sample)
		head = self.invoke(application, REQUEST_METHOD='HEAD')
		self.assertEqual(head['body'], b'')
		self.assertEqual(dict(head['headers'])['Content-Length'], '5')
		self.assertTrue(self.invoke(application, PATH_INFO='/missing')['status'].startswith('404'))

		class Upgrade(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				request.writer.upgrade(Response(status=101))
				return

		application.add(Upgrade)
		self.assertTrue(self.invoke(application)['status'].startswith('501'))
		return

	def test_no_body_statuses_and_repeated_headers(self):
		for status in (
			204,
			205,
			304,
		):
			with self.subTest(status=status):
				class Empty(
					RequestRunner,
					method='GET',
					url='/',
				):
					def run(
						self,
						request,
					):
						response = Response(status=status, body=b'ignored')
						response.props['Set-Cookie'] = 'a=1'
						response.props['Set-Cookie'] = 'b=2'
						return response

				application = Application()
				application.add(Empty)
				result = self.invoke(application)
				self.assertEqual(result['body'], b'')
				self.assertEqual(
					[value for key, value in result['headers'] if key == 'Set-Cookie'],
					[
						'a=1',
						'b=2',
					],
				)
				self.assertEqual(dict(result['headers']).get('Content-Length'), '0' if status == 205 else None)
		return

	def test_error_after_headers_propagates_and_closes_body(self):
		closed = []

		def body():
			try:
				yield b'first'
				raise RuntimeError('stream failed')
			finally:
				closed.append(True)

		class Stream(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				return Response(body=body())

		application = Application()
		application.add(Stream)
		with self.assertLogs('DefEssential.Server', level='ERROR'):
			with self.assertRaisesRegex(RuntimeError, 'stream failed'):
				self.invoke(application)
		self.assertEqual(closed, [True])
		return

	def test_malformed_framing_is_rejected(self):
		for headers in (
			{'CONTENT_LENGTH': '-1'},
			{'CONTENT_LENGTH': '1,1'},
			{
				'CONTENT_LENGTH': '1',
				'HTTP_TRANSFER_ENCODING': 'chunked',
			},
			{'HTTP_TRANSFER_ENCODING': 'gzip'},
		):
			with self.subTest(headers=headers):
				self.assertTrue(self.invoke(Application(), **headers)['status'].startswith('400'))
		return


@skipUnless(find_spec('uvicorn') and find_spec('a2wsgi'), 'Uvicorn 선택적 의존성 필요')
class UvicornTests(TestCase):
	def test_real_http_and_lifecycle(self):
		from uvicorn import Server as HTTPServer

		class Sample(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				request,
			):
				return Response(body=b'OK')

		class Upload(
			RequestRunner,
			method='POST',
			url='/upload',
			body=Body(ChunkedStreamContentReader()),
		):
			def run(
				self,
				request,
			):
				return Response(body=request.body.read())

		class Stream(
			RequestRunner,
			method='GET',
			url='/stream',
		):
			def run(
				self,
				request,
			):
				request.writer.begin(Response(), chunked=True)
				request.writer.write(b'abc')
				request.writer.write(b'def')
				request.writer.end()
				return

		lifecycle = Lifecycle()
		application = Application(exts=(lifecycle,))
		application.add(Sample)
		application.add(Upload)
		application.add(Stream)
		created = Event()
		servers = []
		errors = []

		def create(config):
			server = HTTPServer(config)
			servers.append(server)
			created.set()
			return server

		def run():
			try:
				with UvicornServer('127.0.0.1', 0, application, log_level='critical') as server:
					server.run()
			except BaseException as error:
				errors.append(error)
			return

		with patch('uvicorn.Server', side_effect=create):
			thread = Thread(target=run)
			thread.start()
			try:
				self.assertTrue(created.wait(5))
				server = servers[0]
				deadline = monotonic() + 5
				while not server.started and thread.is_alive() and monotonic() < deadline:
					sleep(0.01)
				self.assertTrue(server.started, errors)
				port = server.servers[0].sockets[0].getsockname()[1]
				connection = HTTPConnection('127.0.0.1', port, timeout=3)
				try:
					connection.request('GET', '/')
					response = connection.getresponse()
					self.assertEqual(response.status, 200)
					self.assertEqual(response.read(), b'OK')
					connection.request(
						'POST',
						'/upload',
						body=iter((
							b'abc',
							b'def',
						)),
						headers={'Content-Type': 'application/octet-stream'},
						encode_chunked=True,
					)
					response = connection.getresponse()
					self.assertEqual(response.status, 200)
					self.assertEqual(response.read(), b'abcdef')
					connection.request('GET', '/stream')
					response = connection.getresponse()
					self.assertEqual(response.status, 200)
					self.assertEqual(response.read(), b'abcdef')
				finally:
					connection.close()
			finally:
				if servers:
					servers[0].should_exit = True
				thread.join(timeout=10)
		self.assertFalse(thread.is_alive())
		self.assertEqual(errors, [])
		self.assertFalse(application.running)
		self.assertEqual(lifecycle.events, [
			'start',
			'stop',
		])
		return

	def test_three_call_styles_clean_up_on_success_and_failure(self):
		for style in (
			'assigned',
			'inline',
			'context',
		):
			for failed in (
				False,
				True,
			):
				with self.subTest(style=style, failed=failed):
					lifecycle = Lifecycle()
					application = Application(exts=(lifecycle,))
					failure = RuntimeError('server failed') if failed else None
					expected = self.assertRaisesRegex(RuntimeError, 'server failed') if failed else nullcontext()
					with redirect_stdout(StringIO()) as output:
						with patch('uvicorn.Server.run', side_effect=failure):
							with expected:
								if style == 'assigned':
									server = UvicornServer('127.0.0.1', 0, application)
									server.run()
								elif style == 'inline':
									UvicornServer('127.0.0.1', 0, application).run()
								else:
									with UvicornServer('127.0.0.1', 0, application) as server:
										server.run()
					text = output.getvalue()
					self.assertEqual(text.count('\nStarting\n'), 1)
					self.assertIn('  Server: Uvicorn\n  Listen:', text)
					self.assertNotIn('PID:', text)
					self.assertIn('Listen: http://127.0.0.1:0', text)
					self.assertIn('Lifecycle: /lifecycle', text)
					self.assertEqual(lifecycle.events, [
						'start',
						'stop',
					])
					self.assertFalse(application.running)
		return

	def test_startup_output_failure_does_not_start_application(self):
		lifecycle = Lifecycle()
		application = Application(exts=(lifecycle,))
		with patch('DefEssential.Adapter.Implements.Uvicorn.Server.startup', side_effect=OSError('output failed')):
			with patch('uvicorn.Server.run') as run:
				with self.assertRaisesRegex(OSError, 'output failed'):
					UvicornServer('127.0.0.1', 8000, application).run()
				run.assert_not_called()
		self.assertEqual(lifecycle.events, [])
		self.assertFalse(application.running)
		return


@skipUnless(name == 'posix' and find_spec('gunicorn'), 'Gunicorn과 POSIX 환경 필요')
class GunicornTests(TestCase):
	def test_workers_classes_and_lifecycle(self):
		self.run_worker_cases((
			(
				'sync',
				'assigned',
			),
			(
				'gthread',
				'inline',
			),
			(
				'class',
				'inline',
			),
			(
				'class',
				'context',
			),
		))
		return

	@skipUnless(find_spec('gevent'), 'gevent 선택적 의존성 필요')
	def test_gevent_workers_and_lifecycle(self):
		self.run_worker_cases((
			(
				'gevent',
				'context',
			),
		))
		return

	def run_worker_cases(
		self,
		cases,
	):
		from DefEssential import __file__ as package_file

		script = '''
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from os import getpid
import sys

source, port, events, worker_class, style = sys.argv[1:]
spec = spec_from_file_location('DefEssential', Path(source) / '__init__.py')
module = module_from_spec(spec)
sys.modules['DefEssential'] = module
spec.loader.exec_module(module)

from DefEssential import (
	Application,
	Body,
	Extension,
	RequestRunner,
	Response,
)
from DefEssential.Adapter.Implements.Gunicorn import Server
from DefEssential.IO.Readers import ChunkedStreamContentReader

def record(event):
	with Path(events).open('a') as output:
		output.write(f'{getpid()}:{event}\\n')

class Lifecycle(Extension):
	def start(
		self,
		app,
	):
		record('start')
	def stop(
		self,
		app,
	):
		record('stop')
	def __call__(
		self,
		app,
		request,
	):
		return Response()

class Sample(
	RequestRunner,
	method='GET',
	url='/',
):
	def run(
		self,
		request,
	):
		return Response(body=b'OK')

class Upload(
	RequestRunner,
	method='POST',
	url='/upload',
	body=Body(ChunkedStreamContentReader()),
):
	def run(
		self,
		request,
	):
		return Response(body=request.body.read())

if worker_class == 'class':
	from gunicorn.workers.gthread import ThreadWorker
	worker_class = ThreadWorker

app = Application(exts=(Lifecycle('/lifecycle'),))
app.add(Sample)
app.add(Upload)
options = {
	'workers': 2,
	'worker_class': worker_class,
	'threads': 1 if worker_class == 'sync' else 2,
	'when_ready': lambda server: record('when_ready'),
	'post_worker_init': lambda worker: record('post_worker_init'),
	'worker_exit': lambda server, worker: record('worker_exit'),
	'errorlog': str(Path(events).with_suffix('.log')),
}
if style == 'assigned':
	server = Server(
		'127.0.0.1',
		int(port),
		app,
		**options,
	)
	server.run()
elif style == 'inline':
	Server(
		'127.0.0.1',
		int(port),
		app,
		**options,
	).run()
else:
	with Server(
		'127.0.0.1',
		int(port),
		app,
		**options,
	) as server:
		server.run()
'''
		for worker_class, style in cases:
			with self.subTest(worker_class=worker_class, style=style):
				with TemporaryDirectory() as directory:
					events = Path(directory) / 'events'
					with socket() as listener:
						listener.bind((
							'127.0.0.1',
							0,
						))
						port = listener.getsockname()[1]
					banner = Path(directory) / 'startup.txt'
					with banner.open('w') as output:
						process = Popen(
							[
								executable,
								'-c',
								script,
								str(Path(package_file).parent),
								str(port),
								str(events),
								worker_class,
								style,
							],
							stdout=output,
						)
					try:
						deadline = monotonic() + 60
						while monotonic() < deadline and process.poll() is None:
							if events.exists() and events.read_text().count(':post_worker_init') == 2:
								break
							sleep(0.02)
						self.assertIsNone(process.poll())
						log = events.with_suffix('.log')
						self.assertTrue(
							events.exists(),
							log.read_text() if log.exists() else 'Gunicorn 로그가 생성되지 않았습니다',
						)
						self.assertEqual(events.read_text().count(':start'), 2)
						connection = HTTPConnection('127.0.0.1', port, timeout=3)
						try:
							connection.request('GET', '/')
							response = connection.getresponse()
							self.assertEqual(response.status, 200)
							self.assertEqual(response.read(), b'OK')
							connection.request(
								'POST',
								'/upload',
								body=iter((
									b'abc',
									b'def',
								)),
								headers={'Content-Type': 'application/octet-stream'},
								encode_chunked=True,
							)
							response = connection.getresponse()
							self.assertEqual(response.status, 200)
							self.assertEqual(response.read(), b'abcdef')
						finally:
							connection.close()
					finally:
						if process.poll() is None:
							process.terminate()
						try:
							process.wait(timeout=15)
						except TimeoutExpired:
							process.kill()
							process.wait(timeout=5)
							raise
					self.assertEqual(process.returncode, 0)
					by_worker = {}
					ready = []
					for line in events.read_text().splitlines():
						pid, event = line.split(':')
						if event == 'when_ready':
							ready.append(pid)
							continue
						by_worker.setdefault(pid, []).append(event)
					self.assertEqual(ready, [str(process.pid)])
					self.assertEqual(len(by_worker), 2)
					text = banner.read_text()
					self.assertEqual(text.count('\nStarting\n'), 1)
					self.assertEqual(text.count('  Server: Gunicorn\n'), 1)
					self.assertEqual(text.count(f'Listen: http://127.0.0.1:{port}'), 1)
					self.assertEqual(text.count('Lifecycle: /lifecycle'), 1)
					self.assertNotIn('PID:', text)
					for sequence in by_worker.values():
						self.assertEqual(sequence, [
							'start',
							'post_worker_init',
							'stop',
							'worker_exit',
						])
		return
