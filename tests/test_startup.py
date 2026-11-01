from contextlib import redirect_stdout
from http.client import HTTPConnection
from io import (
	BytesIO,
	StringIO,
	TextIOWrapper,
)
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from DefChord import (
	Application,
	RequestRunner,
	Response,
)
from DefChord.Adapter.Implements.Python import Server
from DefChord.Startup import (
	LOGO,
	colorize_logo,
	startup,
	supports_color,
)
from DefChord.Extensions import (
	File,
	FileSystem,
	Ping,
)
from DefChord.Utils.FileSystemObject.Implements.FileSystem import (
	Configuration,
	Connection,
)

from test_server import running


class TerminalOutput(StringIO):
	def isatty(self) -> bool:
		return True


class StartupTests(TestCase):
	def test_application_at_extension_path_with_a_different_method(self):
		class Submit(
			RequestRunner,
			method='POST',
			url='/ping',
			name='Submit',
		):
			def run(self, request):
				return Response()

		ping = Ping('/ping')
		app = Application(exts=(ping,))
		app.add(Submit)
		with redirect_stdout(StringIO()) as output:
			startup(
				app,
				'Python',
				'127.0.0.1',
				8000,
			)
		text = output.getvalue()
		self.assertIn('Applications: 1 applications', text)
		self.assertIn('    - Submit\n      POST /ping', text)
		self.assertNotIn('      GET /ping', text)
		self.assertIn('    - Ping(/ping)', text)
		self.assertEqual(app.exts, (ping,))
		return

	def test_handler_names_and_extension_paths(self):
		class Named(
			RequestRunner,
			method='GET',
			url='/named',
			name='Example handler',
		):
			def run(self, request):
				return Response()

		class Unnamed(
			RequestRunner,
			method='GET',
			url='/unnamed',
		):
			def run(self, request):
				return Response()

		with TemporaryDirectory() as directory:
			root = Path(directory).resolve()
			file = root / 'sample.txt'
			file.write_bytes(b'content')
			app = Application(exts=(
				Ping('/ping'),
				File('/file', file),
				FileSystem('/files', Connection(Configuration(directory))),
			))
			app.add(Named)
			app.add(Unnamed)
			with redirect_stdout(StringIO()) as output:
				startup(
					app,
					'Python',
					'127.0.0.1',
					8000,
				)
			text = output.getvalue()
			self.assertIn('    - Example handler\n      GET /named', text)
			self.assertIn(f'    - {Unnamed.__qualname__}\n      GET /unnamed', text)
			self.assertIn('  Applications: 2 applications', text)
			self.assertNotIn('      GET /ping', text)
			self.assertNotIn('      HEAD /ping', text)
			self.assertNotIn('      GET /file', text)
			self.assertNotIn('      GET /files', text)
			self.assertIn(
				'  Extensions: 3 extensions\n' + '\n'.join(
					'    - ' + str(extension) for extension in app.exts
				),
				text,
			)
			self.assertNotIn('Factory.__call__', text)
			self.assertNotIn('Ping: http://', text)
		return

	def test_invalid_handler_names(self):
		for name in (
			'',
			'   ',
			42,
		):
			with self.subTest(name=name):
				with self.assertRaises(ValueError):
					class Invalid(
						RequestRunner,
						method='GET',
						url='/invalid',
						name=name,
					):
						def run(self, request):
							return Response()
		return

	def application(self):
		class Health(
			RequestRunner,
			method='GET',
			url='/health',
		):
			def run(
				self,
				request,
			):
				return Response(body=b'OK')

		app = Application()
		app.add(Health)
		return app

	def test_creation_does_not_print_and_execution_reports_actual_state(self):
		app = self.application()
		output = StringIO()
		with redirect_stdout(output):
			with Server('127.0.0.1', 0, app):
				self.assertEqual(output.getvalue(), '')
			with running(app) as address:
				connection = HTTPConnection(
					*address,
					timeout=3,
				)
				try:
					connection.request('GET', '/health')
					response = connection.getresponse()
					self.assertEqual(response.status, 200)
					self.assertEqual(response.read(), b'OK')
				finally:
					connection.close()
		text = output.getvalue()
		self.assertEqual(text.count('\nStarting\n'), 1)
		self.assertIn('  Server: Python\n  Listen:', text)
		self.assertNotIn('PID:', text)
		self.assertIn(f'Listen: http://127.0.0.1:{address[1]}', text)
		self.assertIn('Applications: 1 applications', text)
		self.assertIn('Health', text)
		self.assertIn('GET /health', text)
		self.assertNotIn('\033[', text)
		return

	def test_application_isolation_and_empty_routes(self):
		with redirect_stdout(StringIO()) as output:
			startup(
				Application(),
				'Python',
				'127.0.0.1',
				8000,
			)
		self.assertIn('Applications: 0 applications', output.getvalue())
		self.assertNotIn('/health', output.getvalue())
		return

	def test_encoded_output_does_not_prevent_http_startup(self):
		for encoding in (
			'cp949',
			'ascii',
			'utf-8',
		):
			with self.subTest(encoding=encoding):
				buffer = BytesIO()
				with TextIOWrapper(buffer, encoding=encoding, errors='strict') as output:
					with redirect_stdout(output):
						with running(self.application()) as address:
							connection = HTTPConnection(*address, timeout=3)
							try:
								connection.request('GET', '/health')
								response = connection.getresponse()
								self.assertEqual(response.status, 200)
								self.assertEqual(response.read(), b'OK')
							finally:
								connection.close()
					output.flush()
					text = buffer.getvalue().decode(encoding).replace('\r\n', '\n')
					self.assertIn('\nStarting\n', text)
					self.assertIn(f'Listen: http://127.0.0.1:{address[1]}', text)
					self.assertIn('GET /health', text)
					if encoding == 'utf-8':
						self.assertIn(LOGO.rstrip(), text)
					else:
						self.assertIn(r'\u2584', text)
		return

	def test_failed_bind_does_not_print_startup(self):
		with patch.object(Server, 'server_bind', side_effect=OSError('바인딩 실패')):
			with redirect_stdout(StringIO()) as output:
				with self.assertRaises(OSError):
					Server('127.0.0.1', 0, Application())
		self.assertEqual(output.getvalue(), '')
		return

	def test_color_and_no_color_including_empty_variable(self):
		for terminal, no_color, colored in (
			(False, None, False),
			(True, None, True),
			(True, '1', False),
			(True, '', False),
		):
			output = TerminalOutput() if terminal else StringIO()
			with patch.dict(environ):
				environ.pop('NO_COLOR', None)
				if no_color is not None:
					environ['NO_COLOR'] = no_color
				with redirect_stdout(output):
					self.assertEqual(supports_color(), colored)
					startup(
						Application(),
						'Python',
						'127.0.0.1',
						8000,
					)
			self.assertEqual('\033[' in output.getvalue(), colored)
		colored_logo = colorize_logo(LOGO)
		self.assertEqual(colored_logo.count('\033[0m'), 5)
		self.assertIn("You don't need to await this.", colored_logo)
		return

	def test_application_and_adapter_metadata_without_a_server_instance(self):
		for server in (
			'Python',
			'Gunicorn',
			'Uvicorn',
		):
			with self.subTest(server=server):
				with redirect_stdout(StringIO()) as output:
					startup(
						self.application(),
						server=server,
						host='::1',
						port=8123,
					)
				text = output.getvalue()
				self.assertIn(f'  Server: {server}\n  Listen:', text)
				self.assertNotIn('PID:', text)
				self.assertIn('Listen: http://[::1]:8123', text)
				self.assertIn('GET /health', text)
		return
