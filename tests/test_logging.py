from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from http.client import HTTPConnection
from importlib import import_module
from io import (
	BytesIO,
	StringIO,
)
from logging import (
	DEBUG,
	ERROR,
	INFO,
	WARNING,
	getLogger,
)
from pathlib import Path
from runpy import run_path
from struct import pack
from subprocess import run
from sys import (
	executable,
	path,
)
from threading import Barrier
from unittest import TestCase
from unittest.mock import (
	Mock,
	patch,
)

from DefEssential import (
	Application,
	ApplicationRequest,
	Extension,
	Request,
	RequestRunner,
	RequestRunnerRequest,
	RequestRunnerRequestError,
	RequestRunnerRequestResponse,
	Response,
	ResponseWriter,
)
from DefEssential.Adapter.Implements.Gunicorn import Server as GunicornServer
from DefEssential.Adapter.Implements.Python.Server import (
	Server,
	ServerRequestHandler,
)
from DefEssential.Adapter.Implements.Uvicorn import Server as UvicornServer
from DefEssential.Adapter.RequestHandler import handle_request
from DefEssential.Extensions import (
	File,
	FileSystem,
	Metrics,
	Ping,
	Specifications,
	Status,
	Swagger,
)
from DefEssential.Runners.RunRequest import RunRequest
from DefEssential.IO.RequestReader import ClientDisconnected
from DefEssential.IO.WebSocket import WebSocket
from DefEssential.IO.WebSocket.WebSocketError import WebSocketError
from DefEssential.IO.WebSocket.WebSocketFrame import WebSocketFrame
from test_server import running


class Echo(
	RequestRunner,
	method='GET',
	url='/sample/:id',
):
	def run(
		self,
		request,
	):
		return Response(body=b'private-response')


def request(
	uri='/sample/private-path?token=private-query',
	method='GET',
	output=None,
):
	writer = ResponseWriter(
		Mock(),
		output if output is not None else BytesIO(),
		method=method,
	)
	return Request(
		'127.0.0.1',
		1,
		method,
		uri,
		headers={
			'Authorization': 'private-auth',
			'Cookie': 'private-cookie',
		},
		writer=writer,
	)


def transmit(
	app,
	value,
):
	handle_request(
		app,
		lambda: value,
		value.writer,
	)
	return


class LoggingTests(TestCase):
	def test_class_loggers_and_explicit_override(self):
		for cls, name in (
			(
				Application,
				'Application',
			),
			(
				RunRequest,
				'RequestRunner',
			),
			(
				Extension,
				'Extension',
			),
			(
				Server,
				'Server',
			),
			(
				ServerRequestHandler,
				'Server',
			),
			(
				GunicornServer,
				'Server',
			),
			(
				UvicornServer,
				'Server',
			),
			(
				File,
				'Extensions.File',
			),
			(
				FileSystem,
				'Extensions.FileSystem',
			),
			(
				Ping,
				'Extensions.Ping',
			),
			(
				Metrics,
				'Extensions.Metrics',
			),
			(
				Status,
				'Extensions.Status',
			),
			(
				Specifications,
				'Extensions.Specifications',
			),
			(
				Swagger,
				'Extensions.Swagger',
			),
		):
			with self.subTest(cls=cls):
				self.assertEqual(cls.logger.name, 'DefEssential.' + name)

		class CustomApplication(Application):
			pass

		self.assertIs(CustomApplication.logger, Application.logger)
		custom = getLogger('Sample.CustomApplication')
		with patch.object(CustomApplication, 'logger', custom):
			with self.assertLogs(custom, level=DEBUG) as logs:
				app = CustomApplication()
				app.start()
				app.stop()
			self.assertTrue(all(record.name == custom.name for record in logs.records))
		return

	def test_lifecycle_does_not_configure_logging_and_stop_is_idempotent(self):
		root = getLogger()
		snapshot = (
			root.level,
			tuple(root.handlers),
			tuple(root.filters),
			Application.logger.level,
			tuple(Application.logger.handlers),
			Application.logger.propagate,
		)
		app = Application()
		app.start()
		app.stop()
		app.stop()
		self.assertEqual(snapshot, (
			root.level,
			tuple(root.handlers),
			tuple(root.filters),
			Application.logger.level,
			tuple(Application.logger.handlers),
			Application.logger.propagate,
		))
		with self.assertLogs('DefEssential.Application', level=INFO) as logs:
			app.start()
			app.stop()
			app.stop()
		self.assertEqual(len(logs.records), 4)
		self.assertTrue(all(record.levelno == INFO for record in logs.records))
		return

	def test_handler_failure_is_not_completed_or_logged_with_traceback(self):
		class Failure(
			RequestRunner,
			method='GET',
			url='/failure',
		):
			def run(
				self,
				request,
			):
				raise ValueError('private-error')

		value = request('/failure')
		with self.assertLogs('DefEssential.RequestRunner', level=DEBUG) as logs:
			with self.assertRaisesRegex(ValueError, 'private-error'):
				RunRequest(Failure).run(value)
		messages = '\n'.join(logs.output)
		self.assertIn('Handler running', messages)
		self.assertIn('Runner failed', messages)
		self.assertIn('phase=runner.run', messages)
		self.assertIn('error_type=ValueError', messages)
		self.assertNotIn('Handler returned', messages)
		self.assertNotIn('Runner response provided', messages)
		self.assertNotIn('private-error', messages)
		self.assertTrue(all(record.exc_info is None for record in logs.records))
		return

	def test_full_request_has_safe_context_and_one_transmission_summary(self):
		app = Application()
		app.add(Echo)
		value = request()
		with self.assertLogs('DefEssential', level=DEBUG) as logs:
			transmit(app, value)
		messages = '\n'.join(logs.output)
		for event in (
			'Application dispatch starting',
			'Application dispatch completed',
			'CORS origin check starting',
			'CORS origin check completed',
			'Handler creating',
			'Handler created',
			'Handler running',
			'Handler returned',
			'CORS response starting',
			'CORS response completed',
			'Response transmission starting',
			'Response body cleaning up',
			'Response body cleaned up',
		):
			self.assertIn(event, messages)
		summaries = [record for record in logs.records if 'HTTP transmission result' in record.getMessage()]
		self.assertEqual(len(summaries), 1)
		self.assertEqual(summaries[0].levelno, INFO)
		self.assertIn('request_id=' + value.id, summaries[0].getMessage())
		self.assertIn('status=200 outcome=completed', summaries[0].getMessage())
		self.assertIn("route='/sample/:id'", messages)
		for private in (
			'private-path',
			'private-query',
			'private-auth',
			'private-cookie',
			'private-response',
		):
			self.assertNotIn(private, messages)
		return

	def test_hook_order_and_request_replacement_are_observable(self):
		class Identity(RequestRunnerRequest):
			def __call__(
				self,
				value,
			):
				return value

		class KeepResponse(RequestRunnerRequestResponse):
			def __call__(
				self,
				value,
				response,
			):
				return response

		class Replace(ApplicationRequest):
			def __call__(
				self,
				value,
			):
				self.replacement = request('/sample/replaced-private')
				self.replacement.response_writer = value.writer
				return self.replacement

		class Hooked(
			Echo,
			method='GET',
			url='/sample/:id',
			on_request=(
				Identity(),
				Identity(),
			),
			on_request_response=KeepResponse(),
		):
			pass

		replacement = Replace()
		app = Application(on_request=replacement)
		app.add(Hooked)
		value = request()
		with self.assertLogs('DefEssential', level=DEBUG) as logs:
			transmit(app, value)
		messages = '\n'.join(logs.output)
		self.assertIn('runner.request_hook.0', messages)
		self.assertIn('runner.request_hook.1', messages)
		self.assertIn('runner.response_hook.0', messages)
		self.assertIn('Request replaced: previous_request_id=' + value.id, messages)
		self.assertIn('request_id=' + replacement.replacement.id, messages)
		summary = next(record.getMessage() for record in logs.records if 'HTTP transmission result' in record.getMessage())
		self.assertIn('request_id=' + value.id, summary)
		self.assertNotIn('replaced-private', messages)
		return

	def test_internal_failure_has_one_final_traceback(self):
		class Observe(RequestRunnerRequestError):
			def __call__(
				self,
				value,
				error,
			):
				return

		class Failure(
			Echo,
			method='GET',
			url='/sample/:id',
			on_request_error=Observe(),
		):
			def run(
				self,
				value,
			):
				raise ValueError('diagnostic-error')

		app = Application()
		app.add(Failure)
		value = request()
		with self.assertLogs('DefEssential', level=DEBUG) as logs:
			transmit(app, value)
		errors = [record for record in logs.records if record.levelno == ERROR]
		self.assertEqual(len(errors), 1)
		self.assertEqual(errors[0].name, 'DefEssential.Server')
		self.assertIsNotNone(errors[0].exc_info)
		self.assertTrue(any(
			'Runner failed' in record.getMessage() and 'phase=runner.run' in record.getMessage()
			for record in logs.records
		))
		self.assertIn('runner.error_hook.0', '\n'.join(logs.output))
		summary = next(record.getMessage() for record in logs.records if 'HTTP transmission result' in record.getMessage())
		self.assertIn('status=500 outcome=completed', summary)
		return

	def test_http_rejections_are_not_warnings(self):
		app = Application()
		app.add(Echo)
		for value, status in (
			(
				request('/missing?token=private-query'),
				404,
			),
			(
				request(method='POST'),
				405,
			),
		):
			with self.subTest(status=status):
				with self.assertLogs('DefEssential', level=DEBUG) as logs:
					transmit(app, value)
				self.assertFalse(any(record.levelno >= WARNING for record in logs.records))
				self.assertIn('status=' + str(status), '\n'.join(logs.output))
				self.assertNotIn('private-query', '\n'.join(logs.output))
				if status == 405:
					self.assertNotIn('private-path', '\n'.join(logs.output))
		return

	def test_failed_or_disconnected_transmission_is_not_successful(self):
		for exception, expected_level, outcome in (
			(
				RuntimeError('private-body-failure'),
				ERROR,
				'failed',
			),
			(
				ConnectionResetError('private-reset'),
				WARNING,
				'disconnected',
			),
			(
				OSError('private-io-failure'),
				ERROR,
				'failed',
			),
		):
			with self.subTest(outcome=outcome, exception=type(exception)):
				def body():
					yield b'first'
					raise exception

				class Stream(
					Echo,
					method='GET',
					url='/sample/:id',
				):
					def run(
						self,
						value,
					):
						return Response(body=body())

				app = Application()
				app.add(Stream)
				value = request()
				with self.assertLogs('DefEssential', level=DEBUG) as logs:
					with self.assertRaises(type(exception)):
						transmit(app, value)
				problems = [record for record in logs.records if record.levelno >= WARNING]
				self.assertEqual(len(problems), 1)
				self.assertEqual(problems[0].levelno, expected_level)
				summary = next(record.getMessage() for record in logs.records if 'HTTP transmission result' in record.getMessage())
				self.assertIn('status=200 outcome=' + outcome, summary)
				self.assertNotIn('outcome=completed', summary)
				if expected_level == WARNING:
					self.assertIsNone(problems[0].exc_info)
					self.assertNotIn('private-reset', '\n'.join(logs.output))
		return

	def test_response_cleanup_failure_is_a_separate_event(self):
		class Body:
			def __iter__(self):
				yield b'one'

			def close(self):
				raise RuntimeError('cleanup failure')

		class Stream(
			Echo,
			method='GET',
			url='/sample/:id',
		):
			def run(
				self,
				value,
			):
				return Response(body=Body())

		app = Application()
		app.add(Stream)
		with self.assertLogs('DefEssential', level=DEBUG) as logs:
			transmit(app, request())
		self.assertIn('outcome=completed', '\n'.join(logs.output))
		errors = [record for record in logs.records if record.levelno == ERROR]
		self.assertEqual(len(errors), 1)
		self.assertIn('Response body cleanup failed', errors[0].getMessage())
		return

	def test_monotonic_duration_and_unavailable_status(self):
		module = import_module('DefEssential.Adapter.RequestHandler')
		with patch.object(module, 'monotonic', side_effect=(10.0, 12.5)):
			with self.assertLogs('DefEssential.Server', level=INFO) as logs:
				value = request()
				with self.assertRaises(ClientDisconnected):
					handle_request(
						Application(),
						Mock(side_effect=ClientDisconnected()),
						value.writer,
					)
		summary = next(record.getMessage() for record in logs.records if 'HTTP transmission result' in record.getMessage())
		self.assertIn('request_id=None method=None status=None', summary)
		self.assertIn('outcome=disconnected duration=2.500000', summary)
		return

	def test_parallel_requests_keep_route_and_id_separate(self):
		barrier = Barrier(2)

		class First(
			Echo,
			method='GET',
			url='/sample/:id',
		):
			def run(
				self,
				value,
			):
				barrier.wait(timeout=3)
				return Response()

		class Second(
			First,
			method='GET',
			url='/other/:id',
		):
			pass

		app = Application()
		app.add(First)
		app.add(Second)
		values = (
			request('/sample/secret-a'),
			request('/other/secret-b'),
		)
		with self.assertLogs('DefEssential', level=DEBUG) as logs:
			with ThreadPoolExecutor(max_workers=2) as executor:
				list(executor.map(lambda value: transmit(app, value), values))
		summaries = [record.getMessage() for record in logs.records if 'HTTP transmission result' in record.getMessage()]
		self.assertEqual(len(summaries), 2)
		for value in values:
			self.assertEqual(sum('request_id=' + value.id in text for text in summaries), 1)
		self.assertNotIn('secret-', '\n'.join(logs.output))
		return

	def test_unmatched_paths_are_not_logged(self):
		for path in (
			'/한글\n\t\r\x00\u2028?token=private',
			'/' + 'x' * 1000,
			'/' + '\x00' * 1000,
		):
			with self.subTest(path=path):
				with self.assertLogs('DefEssential', level=DEBUG) as logs:
					transmit(Application(), request(path))
				self.assertIn('status=404', '\n'.join(logs.output))
				for record in logs.records:
					text = record.getMessage()
					self.assertTrue(text.isprintable())
					self.assertNotIn('private', text)
					self.assertNotIn('path=', text)
		return

	def test_nested_application_keeps_outer_transmission_id(self):
		class Inner(
			Echo,
			method='GET',
			url='/inner/:id',
		):
			pass

		inner = Application()
		inner.add(Inner)

		class Outer(
			Echo,
			method='GET',
			url='/sample/:id',
		):
			def run(
				self,
				value,
			):
				return inner(request('/inner/private-inner-path'))

		outer = Application()
		outer.add(Outer)
		value = request()
		with self.assertLogs('DefEssential.Server', level=INFO) as logs:
			transmit(outer, value)
		self.assertEqual(len(logs.records), 1)
		self.assertIn('request_id=' + value.id, logs.records[0].getMessage())
		self.assertNotIn('private-', logs.records[0].getMessage())
		return

	def test_python_server_reports_actual_port_and_one_safe_summary(self):
		app = Application()
		app.add(Echo)
		with redirect_stdout(StringIO()), self.assertLogs('DefEssential.Server', level=INFO) as logs:
			with running(app) as address:
				connection = HTTPConnection(*address, timeout=3)
				try:
					connection.request('GET', '/sample/private-path?token=private-query')
					response = connection.getresponse()
					self.assertEqual(response.read(), b'private-response')
				finally:
					connection.close()
		self.assertTrue(any(
			'Server ready: adapter=Python' in message and 'port=' + str(address[1]) in message
			for message in logs.output
		))
		self.assertEqual(sum('HTTP transmission result' in message for message in logs.output), 1)
		self.assertNotIn('private-', '\n'.join(logs.output))
		return

	def test_python_bind_failure_is_logged_once_without_false_readiness(self):
		with patch('http.server.ThreadingHTTPServer.server_bind', side_effect=OSError('bind failed')):
			with self.assertLogs('DefEssential.Server', level=DEBUG) as logs:
				with self.assertRaisesRegex(OSError, 'bind failed'):
					Server('127.0.0.1', 0, Application())
		self.assertEqual(len(logs.records), 1)
		self.assertEqual(logs.records[0].levelno, ERROR)
		self.assertIn('Server bind failed', logs.records[0].getMessage())
		return

	def test_debug_disabled_does_not_read_body_for_logging(self):
		body = Mock()
		body.__repr__ = Mock(side_effect=AssertionError('repr is not allowed'))
		app = Application()
		app.add(Echo)
		value = request()
		value.body = body
		with self.assertLogs('DefEssential', level=INFO) as logs:
			transmit(app, value)
		body.read.assert_not_called()
		body.__repr__.assert_not_called()
		self.assertEqual(len(logs.records), 1)
		return

	def test_transmission_summary_for_direct_chunked_head_and_empty_responses(self):
		for mode, method, status in (
			(
				'returned',
				'GET',
				200,
			),
			(
				'direct',
				'GET',
				200,
			),
			(
				'chunked',
				'GET',
				200,
			),
			(
				'returned',
				'HEAD',
				200,
			),
			(
				'returned',
				'GET',
				204,
			),
			(
				'returned',
				'GET',
				205,
			),
			(
				'returned',
				'GET',
				304,
			),
		):
			with self.subTest(mode=mode, method=method, status=status):
				class Output(
					RequestRunner,
					method=method,
					url='/',
				):
					def run(
						self,
						value,
					):
						if mode == 'returned':
							return Response(status=status, body=b'private-response')
						value.writer.begin(Response(status=status), chunked=mode == 'chunked')
						value.writer.write(b'private-response')
						value.writer.end()
						return

				app = Application()
				app.add(Output)
				value = request('/', method=method)
				with self.assertLogs('DefEssential.Server', level=INFO) as logs:
					transmit(app, value)
				self.assertEqual(len(logs.records), 1)
				self.assertIn('status=' + str(status) + ' outcome=completed', logs.records[0].getMessage())
				self.assertTrue(value.writer.ended)
		return

	def test_log_thresholds_preserve_error_visibility(self):
		class Failure(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(
				self,
				value,
			):
				raise RuntimeError('internal diagnostic')

		app = Application()
		app.add(Failure)
		for level in (
			DEBUG,
			INFO,
			WARNING,
			ERROR,
		):
			with self.subTest(level=level):
				with self.assertLogs('DefEssential', level=level) as logs:
					transmit(app, request('/'))
				self.assertEqual(sum(record.levelno == ERROR for record in logs.records), 1)
				self.assertTrue(all(record.levelno >= level for record in logs.records))
				if level == INFO:
					self.assertEqual([record.levelno for record in logs.records], [
						ERROR,
						INFO,
					])
				if level >= WARNING:
					self.assertEqual([record.levelno for record in logs.records], [ERROR])
		return

	def test_websocket_state_logs_exclude_close_reason_and_payload(self):
		value = request('/')
		socket = WebSocket(value, limit=16)
		with patch.object(socket.handshake, 'response', return_value=Response(status=101)):
			with self.assertLogs('DefEssential.IO.WebSocket', level=DEBUG) as logs:
				socket.accept()
				socket.send('private-message')
				socket.receive_close(WebSocketFrame(
					WebSocketFrame.CLOSE,
					pack('!H', 1000) + b'private-close-reason',
				))
		self.assertIn('WebSocket upgraded', '\n'.join(logs.output))
		self.assertIn('WebSocket closed', '\n'.join(logs.output))
		self.assertNotIn('private-', '\n'.join(logs.output))
		other = WebSocket(request('/'), limit=16)
		with patch.object(other.handshake, 'response', return_value=Response(status=101)):
			other.accept()
		with self.assertLogs('DefEssential.IO.WebSocket', level=DEBUG) as logs:
			other.fail(WebSocketError(1002, 'private-protocol-reason'))
		self.assertEqual(logs.records[0].levelno, WARNING)
		self.assertIn('code=1002', logs.records[0].getMessage())
		self.assertNotIn('private-protocol-reason', '\n'.join(logs.output))
		return

	def test_unconfigured_process_preserves_last_resort(self):
		source = Path(__file__).resolve().parents[1] / 'src' / '__init__.py'
		code = (
			'from importlib.util import module_from_spec, spec_from_file_location\n'
			'import logging, sys\n'
			'spec = spec_from_file_location("DefEssential", sys.argv[1])\n'
			'module = module_from_spec(spec)\n'
			'sys.modules["DefEssential"] = module\n'
			'spec.loader.exec_module(module)\n'
			'app = module.Application()\n'
			'app.start()\n'
			'app.stop()\n'
			'assert not logging.getLogger().handlers\n'
			'assert not logging.getLogger("DefEssential").handlers\n'
			'logging.getLogger("DefEssential").warning("last-resort-probe")\n'
		)
		result = run(
			[
				executable,
				'-c',
				code,
				str(source),
			],
			capture_output=True,
			text=True,
			timeout=10,
			check=True,
		)
		self.assertEqual(result.stdout, '')
		self.assertEqual(result.stderr.strip(), 'last-resort-probe')
		return

	def test_sample_startup_configures_only_sample_and_framework_once(self):
		sample = Path(__file__).resolve().parents[1] / 'samples' / 'Sample.py'
		with patch('sys.path', [str(sample.parent.parent), *path]):
			namespace = run_path(str(sample), run_name='sample_logging_test')
		root = getLogger()
		previous_handlers = root.handlers[:]
		previous_level = root.level
		stream = StringIO()
		try:
			setup = namespace['LoggingSetup']()
			setup.handler.setStream(stream)
			app = Application(on_startup=setup)
			self.assertEqual(root.handlers, previous_handlers)
			app.start()
			app.stop()
			app.start()
			app.stop()
			self.assertEqual(root.handlers.count(setup.handler), 1)
			for name in (
				'Sample',
				'Sample.Child',
				'DefEssential',
				'DefEssential.Child',
				'SampleExtra',
				'DefEssentialExtra',
				'External.Library',
			):
				getLogger(name).info('source=%s', name)
			text = stream.getvalue()
			for name in (
				'Sample',
				'Sample.Child',
				'DefEssential',
				'DefEssential.Child',
			):
				self.assertIn(name + ' source=' + name, text)
			for name in (
				'SampleExtra',
				'DefEssentialExtra',
				'External.Library',
			):
				self.assertNotIn(name, text)
			self.assertIn(' INFO ', text)
			self.assertTrue(all(handler in root.handlers for handler in previous_handlers))
		finally:
			for handler in root.handlers[:]:
				if handler not in previous_handlers:
					root.removeHandler(handler)
					handler.close()
			root.setLevel(previous_level)
		return
