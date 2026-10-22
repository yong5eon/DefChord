from contextlib import redirect_stdout
from http.client import HTTPConnection
from io import (
	BytesIO,
	StringIO,
	TextIOWrapper,
)
from os import (
	environ,
	getpid,
)
from unittest import TestCase
from unittest.mock import patch

from DefEssential import (
	Application,
	RequestRunner,
	Response,
	serve,
)
from DefEssential.Startup import (
	LOGO,
	colorize_logo,
	startup,
	supports_color,
)

from test_server import running


class TerminalOutput(StringIO):
	def isatty(self) -> bool:
		return True


class StartupTests(TestCase):
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
		app.register(Health)
		return app

	def test_creation_does_not_print_and_execution_reports_actual_state(self):
		app = self.application()
		output = StringIO()
		with redirect_stdout(output):
			with serve('127.0.0.1', 0, app):
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
		self.assertEqual(text.count('Starting Application'), 1)
		self.assertIn(f'PID: {getpid()}', text)
		self.assertIn(f'Listen: http://127.0.0.1:{address[1]}', text)
		self.assertIn('Handlers: 1 handlers', text)
		self.assertIn('Health', text)
		self.assertIn('GET /health', text)
		self.assertNotIn('\033[', text)
		return

	def test_application_isolation_and_empty_routes(self):
		with redirect_stdout(StringIO()) as output:
			with serve('127.0.0.1', 0, Application()) as server:
				startup(server)
		self.assertIn('Handlers: 0 handlers', output.getvalue())
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
					self.assertIn('Starting Application', text)
					self.assertIn(f'Listen: http://127.0.0.1:{address[1]}', text)
					self.assertIn('GET /health', text)
					if encoding == 'utf-8':
						self.assertIn(LOGO.rstrip(), text)
					else:
						self.assertIn(r'\u2584', text)
		return

	def test_failed_bind_does_not_print_startup(self):
		with patch('DefEssential.Server.Server.server_bind', side_effect=OSError('바인딩 실패')):
			with redirect_stdout(StringIO()) as output:
				with self.assertRaises(OSError):
					serve('127.0.0.1', 0, Application())
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
					with serve('127.0.0.1', 0, Application()) as server:
						startup(server)
			self.assertEqual('\033[' in output.getvalue(), colored)
		colored_logo = colorize_logo(LOGO)
		self.assertEqual(colored_logo.count('\033[0m'), 5)
		self.assertIn("You don't need to await this.", colored_logo)
		return
