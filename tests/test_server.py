from contextlib import contextmanager
from http.client import HTTPConnection
from importlib import import_module
from socket import create_connection
from threading import (
	Event,
	Thread,
)
from time import (
	monotonic,
	sleep,
)
from unittest import TestCase
from unittest.mock import patch

from DefEssential import (
	Application,
	ApplicationStartup,
	Body,
	Extension,
	ExtensionCleanup,
	ExtensionStartup,
	RequestRunner,
	Response,
)
from DefEssential.Adapter.Implements.Python import Server
from DefEssential.IO.Readers import (
	ChunkedStreamContentReader,
	StreamContentReader,
)


@contextmanager
def running(app):
	with Server(
		'127.0.0.1',
		0,
		app,
		poll_interval=0.01,
	) as server:
		thread = Thread(
			target=server.run,
		)
		thread.start()
		try:
			deadline = monotonic() + 5
			while not app.running and thread.is_alive() and monotonic() < deadline:
				sleep(0.001)
			if not app.running:
				raise RuntimeError('테스트 서버가 시작되지 않았습니다')
			yield (
				'127.0.0.1',
				server.server_port,
			)
		finally:
			if thread.is_alive():
				server.shutdown()
				thread.join(timeout=5)
				if thread.is_alive():
					raise RuntimeError('테스트 서버가 종료되지 않았습니다')


class ServerTests(TestCase):
	def test_keyboard_interrupt_stops_application_and_closes_socket(self):
		events = []

		class Startup(ApplicationStartup):
			def __call__(self):
				events.append('application-startup')
				return

		class ExtensionStart(ExtensionStartup):
			def __call__(self):
				events.append('start')
				return

		class ExtensionStop(ExtensionCleanup):
			def __call__(self):
				events.append('stop')
				return

		class Lifecycle(Extension):
			def __call__(
				self,
				request,
			):
				return Response()

		app = Application(
			exts=(Lifecycle(
				on_startup=ExtensionStart(),
				on_cleanup=ExtensionStop(),
			),),
			on_startup=Startup(),
		)
		with Server('127.0.0.1', 0, app) as server:
			def server_startup(*args):
				events.append('server-startup')
				return

			with patch.object(
				import_module(Server.__module__),
				'startup',
				side_effect=server_startup,
			):
				with patch('http.server.ThreadingHTTPServer.serve_forever', side_effect=KeyboardInterrupt):
					with self.assertLogs('DefEssential.Server', level='INFO') as logs:
						server.run()
			self.assertFalse(app.running)
			self.assertEqual(events, [
				'server-startup',
				'application-startup',
				'start',
				'stop',
			])
			self.assertIn('Shutdown requested', logs.output[0])
		self.assertEqual(server.socket.fileno(), -1)
		return

	def test_keyboard_interrupt_does_not_hide_shutdown_errors(self):
		app = Application()
		with Server('127.0.0.1', 0, app) as server:
			with patch.object(import_module(Server.__module__), 'startup'):
				with patch('http.server.ThreadingHTTPServer.serve_forever', side_effect=KeyboardInterrupt):
					with patch.object(app, 'stop', side_effect=RuntimeError('shutdown failed')):
						with self.assertRaisesRegex(RuntimeError, 'shutdown failed'):
							server.run()
		return

	def test_real_http_and_custom_method(self):
		class Sample(
			RequestRunner,
			method='CUSTOM',
			url='/sample/:id',
		):
			def run(
				self,
				request,
			):
				return Response(body=request.parameters['id'].encode())

		app = Application()
		app.add(Sample)
		with running(app) as address:
			connection = HTTPConnection(
				*address,
				timeout=3,
			)
			try:
				connection.request(
					'CUSTOM',
					'/sample/42',
				)
				response = connection.getresponse()
				self.assertEqual(
					response.status,
					200,
				)
				self.assertEqual(
					response.read(),
					b'42',
				)
			finally:
				connection.close()
		return

	def test_post_put_process_before_upload_finishes(self):
		for method in (
			'POST',
			'PUT',
		):
			for chunked in (
				False,
				True,
			):
				with self.subTest(
					method=method,
					chunked=chunked,
				):
					processed = Event()
					received = []

					class Upload(
						RequestRunner,
						method=method,
						url='/upload',
						body=Body(ChunkedStreamContentReader() if chunked else StreamContentReader()),
					):
						def run(
							self,
							request,
						):
							received.append(request.body.read(3))
							processed.set()
							received.append(request.body.read())
							return Response(body=b''.join(received))

					app = Application()
					app.add(Upload)
					with running(app) as address:
						with create_connection(
							address,
							timeout=3,
						) as client:
							framing = 'Transfer-Encoding: chunked' if chunked else 'Content-Length: 6'
							client.sendall((
								f'{method} /upload HTTP/1.1\r\n'
								'Host: localhost\r\n'
								'Content-Type: application/octet-stream\r\n'
								f'{framing}\r\n\r\n'
							).encode('ascii'))
							client.sendall(b'3\r\nabc\r\n' if chunked else b'abc')
							self.assertTrue(
								processed.wait(2),
								'전체 업로드 전에 첫 입력을 처리해야 합니다',
							)
							client.sendall(b'3\r\ndef\r\n0\r\n\r\n' if chunked else b'def')
							with client.makefile('rb') as output:
								self.assertIn(
									b'200',
									output.readline(),
								)
								while output.readline() != b'\r\n':
									pass
								self.assertEqual(
									output.read(),
									b'abcdef',
								)
		return

	def test_missing_content_type_and_ambiguous_framing(self):
		class Upload(
			RequestRunner,
			method='POST',
			url='/upload',
		):
			def run(
				self,
				request,
			):
				return Response()

		app = Application()
		app.add(Upload)
		with running(app) as address:
			for headers in (
				b'Content-Length: 1\r\n',
				b'Content-Length: 1\r\nTransfer-Encoding: chunked\r\n',
				b'Content-Length: 1\r\nContent-Length: 2\r\n',
				b'Content-Length: -1\r\n',
			):
				with self.subTest(headers=headers):
					with create_connection(
						address,
						timeout=3,
					) as client:
						client.sendall(
							b'POST /upload HTTP/1.1\r\nHost: localhost\r\n'
							+ headers + b'\r\nx',
						)
						with client.makefile('rb') as output:
							self.assertIn(
								b'400',
								output.readline(),
							)
		return
