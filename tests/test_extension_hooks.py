from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event
from typing import Sequence
from unittest import TestCase

from DefEssential import (
	Application,
	ApplicationCleanup,
	ApplicationRequest,
	ApplicationRequestError,
	ApplicationRequestResponse,
	ApplicationStartup,
	ClientError,
	Extension,
	ExtensionCleanup,
	ExtensionRequest,
	ExtensionRequestError,
	ExtensionRequestResponse,
	ExtensionStartup,
	Request,
	RequestRunner,
	Response,
	ResponseWriter,
	Route,
)
from DefEssential.Runners.RunExtension import RunExtensionFactory

from test_features import request


class Echo(Extension):
	"""A multi-route extension for tests."""

	def __init__(
		self,
		paths: Sequence[str] = ('/extension',),
		**hooks,
	):
		super().__init__(**hooks)
		self.paths = tuple(paths)
		self.starts = 0
		return

	def startup(
		self,
		application: Application,
	) -> None:
		self.starts += 1
		for path in self.paths:
			application.add_extension_route(
				self,
				Route(
					'GET',
					path,
					RunExtensionFactory(self, 'GET', path)(),
				),
			)
		super().startup(application)
		return

	def __call__(
		self,
		req: Request,
	) -> Response:
		return Response(body=req.uri.encode())


class General(
	RequestRunner,
	method='GET',
	url='/general',
):
	def run(
		self,
		req: Request,
	) -> Response:
		return Response()


class ActionStartup(ExtensionStartup):
	def __init__(
		self,
		action,
	):
		self.action = action
		return

	def __call__(self) -> None:
		return self.action()


class ActionCleanup(ExtensionCleanup):
	def __init__(
		self,
		action,
	):
		self.action = action
		return

	def __call__(self) -> None:
		return self.action()


class ExtensionHookTests(TestCase):
	def start(
		self,
		extension: Extension,
	) -> Application:
		app = Application(exts=(extension,))
		app.start()
		self.addCleanup(app.stop)
		return app

	def test_public_contract_and_instance_registration(self):
		with self.assertRaises(TypeError):
			Extension()  # pyright: ignore[reportAbstractUsage]
		for invalid in (
			(Echo,),
			(object(),),
			None,
			'extension',
		):
			with self.assertRaises(TypeError):
				Application(exts=invalid)  # pyright: ignore[reportArgumentType]
		extension = Echo()
		values = [extension]
		app = Application(exts=values)
		values.clear()
		self.assertEqual(app.exts, (extension,))
		self.assertEqual(extension.starts, 0)
		self.assertEqual(str(extension), 'Echo')
		for name in (
			'bind',
			'route',
			'routes',
			'begin',
			'end',
			'start',
			'stop',
		):
			self.assertFalse(hasattr(extension, name))
		with self.assertRaises(ValueError):
			Application(exts=(extension,))
		with self.assertRaises(ValueError):
			same = Echo()
			Application(exts=(same, same))
		with self.assertRaises(TypeError):
			class Invalid(Echo, on_startup=ActionStartup(lambda: None)):  # pyright: ignore[reportCallIssue, reportGeneralTypeIssues]
				pass
		return

	def test_constructor_hooks_validate_snapshot_and_instance_isolation(self):
		hook = ActionStartup(lambda: None)
		values = [hook]
		first = Echo(on_startup=values)
		second = Echo()
		values.clear()
		self.assertEqual(first.startup_hooks, (hook,))
		self.assertEqual(second.startup_hooks, ())
		self.assertEqual(Echo(on_startup=None).startup_hooks, ())
		self.assertEqual(Echo(on_startup=hook).startup_hooks, (hook,))
		for keyword in (
			'on_startup',
			'on_cleanup',
			'on_request',
			'on_request_response',
			'on_request_error',
		):
			for invalid in (
				'bad',
				b'bad',
				object(),
				[object()],
			):
				with self.subTest(keyword=keyword, invalid=invalid):
					with self.assertRaises(TypeError):
						Echo(**{keyword: invalid})  # pyright: ignore[reportArgumentType]
		return

	def test_lifecycle_order_no_route_and_repeat_start(self):
		events = []

		class Startup(ApplicationStartup):
			def __call__(self):
				events.append('app-start')
				return

		class Cleanup(ApplicationCleanup):
			def __call__(self):
				events.append('app-cleanup')
				return

		first = Echo(
			('/first', '/second'),
			on_startup=ActionStartup(lambda: events.append('first-start')),
			on_cleanup=ActionCleanup(lambda: events.append('first-cleanup')),
		)
		background = Echo(
			(),
			on_startup=ActionStartup(lambda: events.append('background-start')),
			on_cleanup=ActionCleanup(lambda: events.append('background-cleanup')),
		)
		app = Application(
			exts=(first, background),
			on_startup=Startup(),
			on_cleanup=Cleanup(),
		)
		app.add(General)
		response = app(request('/general'))
		assert response is not None
		self.assertEqual(response.status, 200)
		with self.assertRaises(ClientError):
			app(request('/first'))
		routes = app.router.routes
		owned = app.extension_routes
		for count in (
			1,
			2,
		):
			app.start()
			with self.assertRaises(RuntimeError):
				app.start()
			self.assertEqual(first.starts, count)
			self.assertIs(app.exts[0], first)
			self.assertIs(app.router.routes, routes)
			self.assertIs(app.extension_routes, owned)
			self.assertEqual(len(routes), 3)
			response = app(request('/first'))
			assert response is not None
			self.assertEqual(response.body, b'/first')
			app.stop()
			app.stop()
		self.assertEqual(events, [
			'app-start',
			'first-start',
			'background-start',
			'background-cleanup',
			'first-cleanup',
			'app-cleanup',
		] * 2)
		return

	def test_partial_registration_failure_rolls_back_completed_extensions(self):
		events = []
		first = Echo(
			('/first',),
			on_cleanup=ActionCleanup(lambda: events.append('cleaned')),
		)
		conflict = Echo(('/temporary', '/general'))
		last = Echo(('/last',))
		app = Application(exts=(first, conflict, last))
		app.add(General)
		with self.assertRaises(ValueError):
			app.start()
		self.assertEqual(events, ['cleaned'])
		self.assertEqual(last.starts, 0)
		self.assertEqual(app.exts, (first, conflict, last))
		self.assertEqual([route.url for route in app.router.routes], ['/general'])
		self.assertFalse(app.running)
		return

	def test_original_startup_error_is_preserved_despite_rollback_failure(self):
		def fail():
			raise ValueError('startup failed')

		def cleanup_fail():
			raise RuntimeError('cleanup failed')

		app = Application(exts=(
			Echo(('/first',), on_cleanup=ActionCleanup(cleanup_fail)),
			Echo(('/second',), on_startup=ActionStartup(fail)),
		))
		with self.assertLogs('DefEssential.Application', level='ERROR'):
			with self.assertRaisesRegex(ValueError, 'startup failed'):
				app.start()
		self.assertEqual(app.router.routes, [])
		self.assertEqual(app.started_extensions, [])
		app.stop()
		return

	def test_cleanup_continues_between_extensions_but_not_within_event(self):
		events = []

		def fail():
			events.append('last')
			raise ValueError('cleanup failed')

		app = Application(exts=(
			Echo((), on_cleanup=ActionCleanup(lambda: events.append('first'))),
			Echo((), on_cleanup=(
				ActionCleanup(fail),
				ActionCleanup(lambda: events.append('never')),
			)),
		))
		app.start()
		with self.assertLogs('DefEssential.Application', level='ERROR'):
			with self.assertRaisesRegex(ValueError, 'cleanup failed'):
				app.stop()
		self.assertEqual(events, ['last', 'first'])
		self.assertFalse(app.running)
		self.assertFalse(app.lifecycle_transition)
		return

	def test_application_start_failure_does_not_start_extensions(self):
		class Fail(ApplicationStartup):
			def __call__(self):
				raise ValueError('app failed')

		extension = Echo()
		app = Application(exts=(extension,), on_startup=Fail())
		with self.assertRaises(ValueError):
			app.start()
		self.assertEqual(extension.starts, 0)
		self.assertEqual(app.exts, (extension,))
		return

	def test_route_registration_requires_owner_startup(self):
		extension = Echo(())
		app = Application(exts=(extension,))
		route = Route('GET', '/custom', General)
		with self.assertRaises(RuntimeError):
			app.add_extension_route(extension, route)
		app.start()
		try:
			with self.assertRaises(RuntimeError):
				app.add_extension_route(extension, route)
		finally:
			app.stop()
		return

	def test_unhashable_instance_ownership_uses_identity(self):
		class Unhashable(Echo):
			__hash__ = None  # pyright: ignore[reportAssignmentType]

			def __eq__(
				self,
				other,
			):
				return self is other

		app = self.start(Unhashable())
		response = app(request('/extension'))
		assert response is not None
		self.assertEqual(response.status, 200)
		return

	def test_invalid_route_rolls_back_without_losing_registration(self):
		class Invalid(Echo):
			def startup(
				self,
				application,
			):
				application.add_extension_route(self, object())  # pyright: ignore[reportArgumentType]
				return

		extension = Invalid(())
		app = Application(exts=(extension,))
		with self.assertRaises(TypeError):
			app.start()
		self.assertEqual(app.exts, (extension,))
		self.assertEqual(app.router.routes, [])
		return

	def test_extension_lifecycle_cannot_reenter_start_or_stop(self):
		for method in (
			'start',
			'stop',
		):
			class Reenter(Echo):
				def startup(
					self,
					application,
				):
					getattr(application, method)()
					return

			app = Application(exts=(Reenter(()),))
			with self.assertRaises(RuntimeError):
				app.start()
			self.assertFalse(app.running)
			self.assertFalse(app.lifecycle_transition)
		return

	def test_replaced_and_failed_response_bodies_are_closed(self):
		bodies = []

		class Replace(ExtensionRequestResponse):
			def __call__(
				self,
				req,
				response,
			):
				return Response(body=b'replaced')

		class Fail(ExtensionRequestResponse):
			def __call__(
				self,
				req,
				response,
			):
				raise ValueError('response failed')

		class Stream(Echo):
			def __call__(
				self,
				req,
			):
				body = BytesIO(b'original')
				bodies.append(body)
				return Response(body=body)

		app = self.start(Stream(on_request_response=Replace()))
		response = app(request('/extension'))
		assert response is not None
		self.assertEqual(response.body, b'replaced')
		app = self.start(Stream(on_request_response=Fail()))
		with self.assertRaises(ValueError):
			app(request('/extension'))
		self.assertTrue(all(body.closed for body in bodies))
		return

	def test_request_response_transforms_and_error_chaining(self):
		events = []

		class RequestHook(ExtensionRequest):
			def __call__(
				self,
				req,
			):
				events.append('request')
				return request('/changed')

		class ResponseHook(ExtensionRequestResponse):
			def __call__(
				self,
				req,
				response,
			):
				events.append('response:' + req.uri)
				return Response(body=b'changed')

		app = self.start(Echo(
			on_request=RequestHook(),
			on_request_response=ResponseHook(),
		))
		response = app(request('/extension'))
		assert response is not None
		self.assertEqual(response.body, b'changed')
		self.assertEqual(events, ['request', 'response:/changed'])

		class ErrorHook(ExtensionRequestError):
			def __call__(
				self,
				req,
				error,
			):
				raise RuntimeError('error hook failed')

		class Failing(Echo):
			def __call__(
				self,
				req,
			):
				raise ValueError('original')

		app = self.start(Failing(on_request_error=ErrorHook()))
		with self.assertRaisesRegex(RuntimeError, 'error hook failed') as caught:
			app(request('/extension'))
		self.assertIsInstance(caught.exception.__context__, ValueError)
		return

	def test_error_hook_response_skips_extension_hooks_and_continues_outward(self):
		events = []
		response = Response(status=503, body=b'extension recovery')

		class ErrorHook(ExtensionRequestError):
			def __init__(self, result):
				self.result = result
				return

			def __call__(self, req, error):
				events.append('extension-error')
				return self.result

		class ExtensionResponse(ExtensionRequestResponse):
			def __call__(self, req, current):
				raise AssertionError('확장 응답 훅 재실행')

		class ApplicationResponse(ApplicationRequestResponse):
			def __call__(self, req, current):
				events.append('application-response')
				return current

		class Failing(Echo):
			def __call__(self, req):
				raise ValueError('extension failed')

		extension = Failing(
			on_request_error=(
				ErrorHook(None),
				ErrorHook(response),
				ErrorHook(self.fail),
			),
			on_request_response=ExtensionResponse(),
		)
		app = Application(
			exts=(extension,),
			on_request_response=ApplicationResponse(),
		)
		app.start()
		self.addCleanup(app.stop)
		result = app(request('/extension'))
		self.assertIs(result, response)
		self.assertEqual(events, ['extension-error', 'extension-error', 'application-response'])
		return

	def test_extension_error_response_cannot_replace_started_direct_output(self):
		body = BytesIO(b'recovery body')
		response = Response(status=503, body=body)
		writer = ResponseWriter(lambda current, chunked: None, BytesIO())

		class ErrorHook(ExtensionRequestError):
			def __call__(self, req, error):
				return response

		class Failing(Echo):
			def __call__(self, req):
				req.writer.begin(Response(status=202))
				raise ValueError('direct output failed')

		app = self.start(Failing(on_request_error=ErrorHook()))
		req = request('/extension')
		req.response_writer = writer
		with self.assertRaisesRegex(RuntimeError, 'starting direct output'):
			app(req)
		self.assertEqual(writer.status, 202)
		self.assertTrue(body.closed)
		return

	def test_invalid_results_are_observed_inside_extension_boundary(self):
		errors = []

		class ErrorHook(ExtensionRequestError):
			def __call__(
				self,
				req,
				error,
			):
				errors.append(error)
				return

		class BadRequest(ExtensionRequest):
			def __call__(
				self,
				req,
			):
				return None

		class BadResponse(ExtensionRequestResponse):
			def __call__(
				self,
				req,
				response,
			):
				return None

		for hooks in (
			{'on_request': BadRequest()},
			{'on_request_response': BadResponse()},
		):
			app = self.start(Echo(on_request_error=ErrorHook(), **hooks))  # pyright: ignore[reportArgumentType]
			with self.assertRaises(TypeError):
				app(request('/extension'))
		self.assertEqual(len(errors), 2)
		return

	def test_direct_output_cannot_be_replaced(self):
		class Replace(ExtensionRequestResponse):
			def __call__(
				self,
				req,
				response,
			):
				return Response()

		class Direct(Echo):
			def __call__(
				self,
				req,
			):
				req.writer.response(Response(body=b'direct'))
				return None

		app = self.start(Direct(on_request_response=Replace()))
		req = request('/extension')
		req.response_writer = ResponseWriter(
			lambda response, chunked: None,
			BytesIO(),
		)
		with self.assertRaisesRegex(TypeError, 'direct output'):
			app(req)
		return

	def test_request_scope_restores_outer_request_after_nested_dispatch(self):
		observed = []
		original = request('/incoming')
		nested = request('/inner')

		class Replace(ApplicationRequest):
			def __call__(
				self,
				req,
			):
				return request('/outer') if req is original else req

		app = Application(on_request=Replace())

		class Inner(RequestRunner, method='GET', url='/inner'):
			def run(
				self,
				req,
			):
				observed.append(app.hook_context.request)
				return Response()

		class Outer(RequestRunner, method='GET', url='/outer'):
			def run(
				self,
				req,
			):
				observed.append(app.hook_context.request)
				app(nested)
				observed.append(app.hook_context.request)
				return Response()

		app.add(Inner)
		app.add(Outer)
		app(original)
		self.assertEqual(observed, [original, nested, original])
		self.assertIsNone(app.hook_context.request)
		return


class RequestHookRegistrationTests(TestCase):
	def instrument(
		self,
		events,
		*,
		fail_start=False,
		fail_cleanup=False,
		explicit_remove=True,
	):
		class RequestHook(ApplicationRequest):
			def __call__(
				self,
				req,
			):
				events.append('dynamic-request')
				return req

		class ResponseHook(ApplicationRequestResponse):
			def __call__(
				self,
				req,
				response,
			):
				events.append('dynamic-response')
				return response

		class ErrorHook(ApplicationRequestError):
			def __call__(
				self,
				req,
				error,
			):
				events.append('dynamic-error')
				return

		class Instrument(Echo):
			def startup(
				self,
				application,
			):
				self.application = application
				self.token = application.add_request_hooks(
					on_request=RequestHook(),
					on_request_response=ResponseHook(),
					on_request_error=ErrorHook(),
				)
				super().startup(application)
				if fail_start:
					raise ValueError('instrument startup failed')
				return

			def cleanup(self):
				if explicit_remove:
					self.application.remove_request_hooks(self.token)
				if fail_cleanup:
					raise ValueError('instrument cleanup failed')
				super().cleanup()
				return

		return Instrument(())

	def test_dynamic_hooks_precede_constructor_hooks_and_restart_without_duplicates(self):
		events = []

		class Static(ApplicationRequest):
			def __call__(
				self,
				req,
			):
				events.append('static-request')
				return req

		extension = self.instrument(events)
		app = Application(exts=(extension,), on_request=Static())
		app.add(General)
		for _ in range(2):
			app.start()
			self.assertEqual(len(app.request_hook_registrations), 1)
			app(request('/general'))
			with self.assertRaises(ClientError):
				app(request('/missing'))
			app.stop()
			self.assertEqual(app.request_hook_registrations, [])
		self.assertEqual(events, [
			'dynamic-request',
			'static-request',
			'dynamic-response',
			'dynamic-request',
			'static-request',
			'dynamic-error',
		] * 2)
		return

	def test_failing_owner_and_later_extension_startup_roll_back_dynamic_hooks(self):
		for fail_own in (
			True,
			False,
		):
			extension = self.instrument([], fail_start=fail_own)

			def fail():
				raise ValueError('later startup failed')

			app = Application(exts=(
				extension,
				Echo((), on_startup=ActionStartup(fail)),
			))
			with self.assertRaises(ValueError):
				app.start()
			self.assertEqual(app.request_hook_registrations, [])
			self.assertEqual(len(app.exts), 2)
			self.assertEqual(app.router.routes, [])
		return

	def test_cleanup_failure_still_removes_owner_hooks(self):
		extension = self.instrument([], fail_cleanup=True, explicit_remove=False)
		app = Application(exts=(extension,))
		app.start()
		with self.assertLogs('DefEssential.Application', level='ERROR'):
			with self.assertRaises(ValueError):
				app.stop()
		self.assertEqual(app.request_hook_registrations, [])
		return

	def test_in_flight_request_keeps_hook_snapshot_after_stop(self):
		events = []
		entered = Event()
		release = Event()

		class Pause(ApplicationRequest):
			def __call__(
				self,
				req,
			):
				entered.set()
				if not release.wait(timeout=5):
					raise TimeoutError('Request was not released')
				return req

		extension = self.instrument(events)
		app = Application(exts=(extension,), on_request=Pause())
		app.add(General)
		app.start()
		self.addCleanup(app.stop)
		with ThreadPoolExecutor(max_workers=1) as executor:
			future = executor.submit(app, request('/general'))
			try:
				self.assertTrue(entered.wait(timeout=5))
				app.stop()
				self.assertEqual(app.request_hook_registrations, [])
			finally:
				release.set()
			response = future.result(timeout=5)
		assert response is not None
		self.assertEqual(response.status, 200)
		self.assertEqual(events, ['dynamic-request', 'dynamic-response'])
		return

	def test_registration_and_removal_are_lifecycle_scoped(self):
		app = Application()
		with self.assertRaises(RuntimeError):
			app.add_request_hooks()
		with self.assertRaises(RuntimeError):
			app.remove_request_hooks(object())  # pyright: ignore[reportArgumentType]
		return

	def test_duplicate_hooks_and_wrong_token_owner_are_rejected(self):
		events = []
		first = self.instrument(events)

		class Misuse(Echo):
			def startup(
				self,
				application,
			):
				with case.assertRaises(ValueError):
					application.remove_request_hooks(first.token)
				with case.assertRaises(TypeError):
					application.add_request_hooks(on_request=None)  # pyright: ignore[reportArgumentType]
				with case.assertRaises(ValueError):
					application.add_request_hooks(on_request=first.token.request)
				super().startup(application)
				return

		case = self
		app = Application(exts=(first, Misuse(())))
		app.start()
		self.addCleanup(app.stop)
		return

	def test_duplicate_static_hooks_and_double_remove_are_explicit_errors(self):
		class Hook(ApplicationRequest):
			def __call__(
				self,
				req,
			):
				return req

		hook = Hook()
		case = self

		class Misuse(Echo):
			def startup(
				self,
				application,
			):
				with case.assertRaises(ValueError):
					application.add_request_hooks(on_request=hook)
				fresh = Hook()
				with case.assertRaises(ValueError):
					application.add_request_hooks(on_request=(fresh, fresh))
				token = application.add_request_hooks(on_request=fresh)
				application.remove_request_hooks(token)
				with case.assertRaises(ValueError):
					application.remove_request_hooks(token)
				with case.assertRaises(TypeError):
					application.remove_request_hooks(object())  # pyright: ignore[reportArgumentType]
				super().startup(application)
				return

		app = Application(exts=(Misuse(()),), on_request=hook)
		app.start()
		self.addCleanup(app.stop)
		self.assertEqual(app.request_hook_registrations, [])
		return
