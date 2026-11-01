from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from importlib import import_module
from json import loads
from logging import getLogger
from pathlib import Path
from sys import path
from threading import Barrier
from typing import Optional
from unittest import TestCase
from unittest.mock import (
	Mock,
	patch,
)

from DefChord import (
	Application,
	ApplicationRequest,
	ApplicationRequestResponse,
	ExtensionCleanup,
	ExtensionRequest,
	ExtensionRequestError,
	ExtensionRequestResponse,
	ExtensionStartup,
	Request,
	RequestRunner,
	Response,
	ResponseWriter,
)
from DefChord.Extensions import (
	File,
	FileSystem,
	MetricsCollector,
	Metrics,
	Ping,
	Specifications,
	Status,
	Swagger,
)
from DefChord.Extensions.FileSystem import FileSystemRoute
from DefChord.Utils.FileSystemObject.Implements.FileSystem import (
	Configuration,
	Connection,
)


RESOURCES = Path(__file__).resolve().parents[1] / 'samples' / 'res'


def request(
	uri: str,
	method: str = 'GET',
) -> Request:
	return Request(
		'127.0.0.1',
		1,
		method,
		uri,
	)


class Echo(
	RequestRunner,
	method='GET',
	url='/echo/:id',
):
	def run(
		self,
		request: Request,
	) -> Response:
		return Response(body=request.parameters['id'].encode())


class AddJpeg(ExtensionRequest):
	def __call__(
		self,
		request: Request,
	) -> Request:
		request.params['path'] += '.jpg'
		return request


class ReplaceResponse(ExtensionRequestResponse):
	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		if response is None:
			return None
		return Response(body=b'replaced')


class FailResponse(ApplicationRequestResponse):
	def __call__(
		self,
		request: Request,
		response: Response,
	) -> Response:
		raise RuntimeError('response hook failed')


class BuiltinExtensionTests(TestCase):
	def test_builtin_constructor_hooks_and_prepared_startup(self):
		for create in (
			lambda **hooks: Ping('/builtin', **hooks),
			lambda **hooks: File('/builtin', RESOURCES / 'html' / 'welcome.html', **hooks),
			lambda **hooks: FileSystem('/builtin', Mock(), **hooks),
			lambda **hooks: Status('/builtin', metrics_uri='/metrics', **hooks),
			lambda **hooks: Swagger('/builtin', spec_uri='/doc', **hooks),
			lambda **hooks: Specifications('/builtin', **hooks),
			lambda **hooks: Metrics('/builtin', **hooks),
		):
			startup = Mock(spec=ExtensionStartup, return_value=None)
			cleanup = Mock(spec=ExtensionCleanup, return_value=None)
			on_request = Mock(spec=ExtensionRequest)
			on_response = Mock(spec=ExtensionRequestResponse)
			on_error = Mock(spec=ExtensionRequestError)
			extension = create(
				on_startup=startup,
				on_cleanup=cleanup,
				on_request=on_request,
				on_request_response=on_response,
				on_request_error=on_error,
			)
			with self.subTest(extension=type(extension).__name__):
				app = Application(exts=(extension,))
				self.assertIn('/builtin', str(extension))
				self.assertEqual(app.extension_routes, [])
				self.assertEqual(extension.request_hooks, (on_request,))
				self.assertEqual(extension.request_response_hooks, (on_response,))
				self.assertEqual(extension.request_error_hooks, (on_error,))

				def prepared() -> None:
					self.assertEqual(len(app.extension_routes), 2)
					if isinstance(extension, FileSystem):
						assert isinstance(extension.connection, Mock)
						extension.connection.connect.assert_called_once()
					return

				startup.side_effect = prepared
				app.start()
				app.stop()
				startup.assert_called_once_with()
				cleanup.assert_called_once_with()
		return

	def test_filesystem_user_startup_failure_closes_partial_connection(self):
		connection = Mock()
		startup = Mock(spec=ExtensionStartup, side_effect=ValueError('startup failed'))
		extension = FileSystem(
			'/files',
			connection,
			on_startup=startup,
		)
		app = Application(exts=(extension,))
		with self.assertRaisesRegex(ValueError, 'startup failed'):
			app.start()
		connection.connect.assert_called_once()
		connection.close.assert_called_once()
		self.assertEqual(app.extension_routes, [])
		self.assertFalse(app.running)
		return

	def test_filesystem_cleanup_attempts_close_and_preserves_user_error(self):
		connection = Mock()
		connection.close.side_effect = RuntimeError('close failed')
		cleanup = Mock(spec=ExtensionCleanup, side_effect=ValueError('cleanup failed'))
		app = Application(exts=(FileSystem(
			'/files',
			connection,
			on_cleanup=cleanup,
		),))
		app.start()
		with self.assertLogs(level='ERROR'):
			with self.assertRaisesRegex(ValueError, 'cleanup failed'):
				app.stop()
		cleanup.assert_called_once_with()
		connection.close.assert_called_once()
		return

	def test_metrics_default_collector_and_scoped_extension_hooks(self):
		on_request = Mock(spec=ExtensionRequest, side_effect=lambda req: req)
		metrics = Metrics(
			'/metrics',
			on_request=on_request,
		)
		app = Application(exts=(
			metrics,
			Ping('/ping'),
		))
		app.start()
		try:
			app(request('/ping'))
			on_request.assert_not_called()
			self.assertEqual(metrics.collector.snapshot()['requests']['GET /ping']['success'], 1)
			app(request('/metrics'))
			on_request.assert_called_once()
			self.assertIsNotNone(metrics.hook_token)
		finally:
			app.stop()
		self.assertIsNone(metrics.hook_token)
		self.assertEqual(app.request_hook_registrations, [])
		return

	def test_metrics_startup_failure_unregisters_and_restart_is_not_duplicated(self):
		startup = Mock(
			spec=ExtensionStartup,
			side_effect=[
				ValueError('startup failed'),
				None,
			],
		)
		metrics = Metrics(
			'/metrics',
			on_startup=startup,
		)
		app = Application(exts=(
			metrics,
			Ping('/ping'),
		))
		with self.assertRaisesRegex(ValueError, 'startup failed'):
			app.start()
		self.assertIsNone(metrics.hook_token)
		self.assertEqual(app.request_hook_registrations, [])
		self.assertEqual(app.extension_routes, [])
		app.start()
		try:
			app(request('/ping'))
			self.assertEqual(metrics.collector.snapshot()['requests']['GET /ping']['success'], 1)
			self.assertEqual(len(app.request_hook_registrations), 1)
		finally:
			app.stop()
		return

	def test_metrics_cleanup_hook_failure_still_unregisters(self):
		cleanup = Mock(spec=ExtensionCleanup, side_effect=ValueError('cleanup failed'))
		metrics = Metrics(
			'/metrics',
			on_cleanup=cleanup,
		)
		app = Application(exts=(metrics,))
		app.start()
		with self.assertLogs(level='ERROR'):
			with self.assertRaisesRegex(ValueError, 'cleanup failed'):
				app.stop()
		cleanup.assert_called_once_with()
		self.assertIsNone(metrics.hook_token)
		self.assertEqual(app.request_hook_registrations, [])
		return

	def test_ping_live_state_and_same_instance_restart(self):
		extension = Ping('/ping')
		app = Application(exts=(extension,))
		self.assertEqual(app.exts, (extension,))
		app.start()
		first = app.exts[0]
		assert isinstance(first, Ping)
		self.assertIs(first.application, app)
		response = app(request('/ping'))
		assert response is not None
		self.assertEqual(response.status, 200)
		app.stop()
		self.assertEqual(first(request('/ping')).status, 503)
		app.start()
		try:
			self.assertIs(first, app.exts[0])
			self.assertEqual(len(app.extension_routes), 2)
		finally:
			app.stop()
		return

	def test_page_extensions_and_validation(self):
		app = Application(exts=(
			Status(
				'/status',
				metrics_uri='/metrics?x=1&y=2',
			),
			Swagger(
				'/swagger',
				spec_uri='/doc',
			),
		))
		app.start()
		try:
			status = app(request('/status'))
			assert status is not None
			self.assertIn(b'/metrics?x=1&amp;y=2', status.body)
			self.assertIn('Application 처리 완료까지 측정'.encode(), status.body)
			self.assertNotIn('응답 전송이 끝나지 않은 요청'.encode(), status.body)
			self.assertNotIn('전송 실패·연결 해제 포함'.encode(), status.body)
			swagger = app(request('/swagger'))
			assert swagger is not None
			self.assertIn(b'/doc', swagger.body)
		finally:
			app.stop()
		for extension in (
			Ping,
			Specifications,
		):
			with self.assertRaises(ValueError):
				extension('/bad/:id')
		return

	def test_file_hooks_and_head_routes(self):
		app = Application(exts=(File(
			'/file',
			RESOURCES / 'html' / 'welcome.html',
			on_request_response=ReplaceResponse(),
		),))
		app.start()
		try:
			response = app(request('/file'))
			assert response is not None
			self.assertEqual(response.body, b'replaced')
			head = app(request('/file', 'HEAD'))
			assert head is not None
			self.assertEqual(head.body, b'replaced')
		finally:
			app.stop()
		return

	def test_filesystem_route_decoding_lifecycle_and_hooks(self):
		connection = Connection(Configuration(str(RESOURCES / 'images')))
		with (
			patch.object(connection, 'connect') as connect,
			patch.object(connection, 'close') as close,
		):
			app = Application(exts=(FileSystem(
				'/images',
				connection,
				on_request=AddJpeg(),
				on_request_response=ReplaceResponse(),
			),))
			connect.assert_not_called()
			app.start()
			connect.assert_called_once()
			try:
				self.assertTrue(all(isinstance(route, FileSystemRoute) for route in app.extension_routes))
				response = app(request('/images/%73ample'))
				assert response is not None
				self.assertEqual(response.body, b'replaced')
				head = app(request('/images/sample', 'HEAD'))
				assert head is not None
				self.assertEqual(head.body, b'replaced')
				self.assertEqual(app.extension_routes[0].match('/images/a%2Fb'), {'path': 'a/b'})
			finally:
				app.stop()
			close.assert_called_once()
		return

	def test_filesystem_instance_hooks_are_not_overwritten(self):
		first = Mock()
		second = Mock()
		apps = (
			Application(exts=(FileSystem('/one', first),)),
			Application(exts=(FileSystem('/two', second),)),
		)
		for app in apps:
			app.start()
		apps[0].stop()
		first.close.assert_called_once()
		second.close.assert_not_called()
		apps[1].stop()
		second.close.assert_called_once()
		return

	def test_filesystem_start_failure_preserves_original_error_when_cleanup_fails(self):
		connection = Mock()
		connection.connect.side_effect = ValueError('connect failed')
		connection.close.side_effect = RuntimeError('close failed')
		app = Application(exts=(FileSystem('/files', connection),))
		with self.assertLogs('Extension.FileSystem', level='ERROR'):
			with self.assertRaisesRegex(ValueError, 'connect failed'):
				app.start()
		connection.close.assert_called_once()
		self.assertFalse(app.running)
		self.assertEqual(app.router.routes, [])
		return

	def test_specifications_live_routes_and_explicit_ownership(self):
		app = Application(exts=(
			Specifications('/doc'),
			Ping('/ping'),
		))
		app.add(Echo)
		app.start()
		try:
			spec = next(extension for extension in app.exts if isinstance(extension, Specifications))
			self.assertIs(spec.application, app)
			self.assertEqual(set(spec.document()['paths']), {'/echo/{id}'})
			response = app(request('/doc'))
			assert response is not None
			assert isinstance(response.body, bytes)
			self.assertEqual(loads(response.body)['openapi'], '3.1.0')
		finally:
			app.stop()
		return

	def metrics_application(
		self,
		collector: MetricsCollector,
		*,
		response_hooks=(),
	) -> Application:
		app = Application(
			exts=(
				Metrics(
					'/metrics',
					collector=collector,
				),
				Ping('/ping'),
			),
			on_request_response=response_hooks,
		)
		app.add(Echo)
		return app

	def test_metrics_live_templates_unmatched_and_restarts(self):
		collector = MetricsCollector()
		app = self.metrics_application(collector)
		app.start()
		try:
			app(request('/echo/123'))
			app(request('/ping'))
			with self.assertRaises(Exception):
				app(request('/missing'))
			stats = collector.snapshot()['requests']
			self.assertEqual(stats['GET /echo/:id']['success'], 1)
			self.assertEqual(stats['GET /ping']['success'], 1)
			self.assertEqual(stats['<unmatched>']['failure'], 1)
			self.assertTrue(all(stats['active'] == 0 for stats in stats.values()))
			self.assertIn('excludes response transfer', collector.render())
			instance = collector.instance
		finally:
			app.stop()
		app.start()
		try:
			self.assertNotEqual(instance, collector.instance)
			self.assertEqual(collector.snapshot()['requests']['GET /ping']['success'], 0)
		finally:
			app.stop()
		return

	def test_metrics_late_response_error_is_not_counted_twice(self):
		collector = MetricsCollector()
		app = self.metrics_application(
			collector,
			response_hooks=FailResponse(),
		)
		app.start()
		try:
			with self.assertRaisesRegex(RuntimeError, 'response hook failed'):
				app(request('/ping'))
			stats = collector.snapshot()['requests']['GET /ping']
			self.assertEqual(stats['active'], 0)
			self.assertEqual(stats['success'], 0)
			self.assertEqual(stats['failure'], 1)
		finally:
			app.stop()
		return

	def test_metrics_tracks_replaced_requests_and_response_hook_failures(self):
		class Replace(ApplicationRequest):
			def __call__(
				self,
				req: Request,
			) -> Request:
				return request('/ping')

		for fail in (
			False,
			True,
		):
			with self.subTest(fail=fail):
				collector = MetricsCollector()
				app = Application(
					exts=(
						Metrics('/metrics', collector=collector),
						Ping('/ping'),
					),
					on_request=Replace(),
					on_request_response=FailResponse() if fail else (),
				)
				app.start()
				try:
					if fail:
						with self.assertRaisesRegex(RuntimeError, 'response hook failed'):
							app(request('/incoming'))
					else:
						response = app(request('/incoming'))
						assert response is not None
						self.assertEqual(response.status, 200)
					stats = collector.snapshot()['requests']['<unmatched>']
					self.assertEqual(stats['active'], 0)
					self.assertEqual(stats['success'], int(not fail))
					self.assertEqual(stats['failure'], int(fail))
					self.assertEqual(collector.observations, {})
				finally:
					app.stop()
		return

	def test_metrics_request_scope_is_isolated_for_concurrent_and_nested_calls(self):
		collector = MetricsCollector()
		barrier = Barrier(2)

		class Replace(ApplicationRequest):
			def __call__(
				self,
				req: Request,
			) -> Request:
				if req.path == '/concurrent':
					barrier.wait(timeout=3)
					return request('/ping')
				return request('/nested') if req.path == '/outer' else req

		app = Application(
			exts=(
				Metrics('/metrics', collector=collector),
				Ping('/ping'),
			),
			on_request=Replace(),
		)

		class Nested(
			RequestRunner,
			method='GET',
			url='/nested',
		):
			def run(
				self,
				req: Request,
			) -> Response:
				response = app(request('/ping'))
				assert response is not None
				return response

		app.add(Nested)
		app.start()
		try:
			with ThreadPoolExecutor(max_workers=2) as executor:
				futures = [
					executor.submit(app, request('/concurrent'))
					for _ in range(2)
				]
				statuses = []
				for future in futures:
					response = future.result(timeout=5)
					assert response is not None
					statuses.append(response.status)
				self.assertEqual(statuses, [
					200,
					200,
				])
			response = app(request('/outer'))
			assert response is not None
			self.assertEqual(response.status, 200)
			stats = collector.snapshot()['requests']
			self.assertEqual(stats['<unmatched>']['success'], 3)
			self.assertEqual(stats['GET /ping']['success'], 1)
			self.assertTrue(all(value['active'] == 0 for value in stats.values()))
			self.assertEqual(collector.observations, {})
		finally:
			app.stop()
		return

	def test_metrics_direct_output_status_and_idempotent_error(self):
		collector = MetricsCollector()
		app = self.metrics_application(collector)
		app.start()
		try:
			req = request('/ping')
			req.response_writer = ResponseWriter(
				lambda response, chunked: None,
				BytesIO(),
			)
			req.writer.status = 503
			collector.on_request(req)
			collector.on_request_response(req, None)
			collector.on_request_error(req, RuntimeError('failed'))
			stats = collector.snapshot()['requests']['GET /ping']
			self.assertEqual(stats['active'], 0)
			self.assertEqual(stats['failure'], 1)
		finally:
			app.stop()
		return

	def test_metrics_collector_application_isolation(self):
		first = MetricsCollector()
		second = MetricsCollector()
		apps = (
			self.metrics_application(first),
			self.metrics_application(second),
		)
		for app in apps:
			app.start()
		try:
			apps[0](request('/ping'))
			self.assertEqual(first.snapshot()['requests']['GET /ping']['success'], 1)
			self.assertEqual(second.snapshot()['requests']['GET /ping']['success'], 0)
		finally:
			for app in apps:
				app.stop()
		return

	def test_sample_application_and_document_script(self):
		root = getLogger()
		handlers = root.handlers[:]
		level = root.level

		def restore_logging():
			for handler in root.handlers[:]:
				if handler not in handlers:
					root.removeHandler(handler)
					handler.close()
			root.setLevel(level)
			return

		self.addCleanup(restore_logging)
		with patch('sys.path', [str(RESOURCES.parents[1]), *path]):
			sample = import_module('samples.Sample')
			script = import_module('samples.scripts.DescriptionToFile')
		app = sample.create_application()
		app.start()
		try:
			self.assertEqual(app(request('/ping')).status, 200)
			self.assertEqual(loads(app(request('/api/doc')).body)['openapi'], '3.1.0')
		finally:
			app.stop()
		output = Mock()
		with (
			patch.object(script, 'create_application', return_value=app),
			patch.object(script, 'ArgumentParser') as parser,
		):
			parser.return_value.parse_args.return_value.output = output
			script.main()
		self.assertFalse(app.running)
		self.assertEqual(loads(output.write_text.call_args.args[0])['openapi'], '3.1.0')
		return
