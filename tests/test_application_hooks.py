from io import BytesIO
from typing import Any
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
	ExtensionStartup,
	Request,
	RequestRunnerRequest,
	RequestReader,
	RequestRunner,
	Response,
	RequestRunnerRequestResponse,
)
from DefEssential.IO.ResponseWriter import ResponseWriter
from DefEssential.Adapter.RequestHandler import handle_request


class Lifecycle(Extension):
	"""Run per-instance lifecycle hooks without routes."""

	def __init__(
		self,
		events,
		label='',
		fail_cleanup=False,
	):
		suffix = ':' + label if label else ''

		class Startup(ExtensionStartup):
			def __call__(self):
				events.append('extension-start' + suffix)
				return

		class Cleanup(ExtensionCleanup):
			def __call__(self):
				events.append('extension-cleanup' + suffix)
				if fail_cleanup:
					raise ValueError(label)
				return

		super().__init__(
			on_startup=Startup(),
			on_cleanup=Cleanup(),
		)
		return

	def __call__(
		self,
		req,
	):
		return Response()


def request(uri='/hook', writer=None):
	return Request(
		address='127.0.0.1',
		port=1234,
		method='GET',
		uri=uri,
		reader=RequestReader(
			BytesIO(),
			size=0,
		),
		writer=writer,
	)


class ApplicationHookTests(TestCase):
	def test_hook_inputs_are_validated_and_snapshotted(self):
		class Startup(ApplicationStartup):
			def __call__(self):
				return

		first = Startup()
		second = Startup()
		hooks = [first]
		app = Application(on_startup=hooks)
		hooks.append(second)
		self.assertEqual(app.startup_hooks, (first,))
		self.assertEqual(Application(on_startup=first).startup_hooks, (first,))
		invalid_inputs: tuple[Any, ...] = (
			None,
			'startup',
			(first, object()),
			object(),
		)
		for invalid in invalid_inputs:
			with self.subTest(invalid=invalid):
				with self.assertRaises(TypeError):
					Application(on_startup=invalid)
		return

	def test_lifecycle_hooks_wrap_extension_lifecycle(self):
		events = []

		class Startup(ApplicationStartup):
			def __call__(self):
				events.append('application-start')

		class Cleanup(ApplicationCleanup):
			def __call__(self):
				events.append('application-cleanup')

		app = Application(
			exts=(
				Lifecycle(
					events,
					'/first',
				),
				Lifecycle(
					events,
					'/last',
				),
			),
			on_startup=Startup(),
			on_cleanup=Cleanup(),
		)
		app.start()
		app.stop()
		self.assertEqual(events, [
			'application-start',
			'extension-start:/first',
			'extension-start:/last',
			'extension-cleanup:/last',
			'extension-cleanup:/first',
			'application-cleanup',
		])
		return

	def test_startup_failure_does_not_start_or_cleanup_extensions(self):
		events = []

		class Startup(ApplicationStartup):
			def __call__(self):
				events.append('application-start')
				raise ValueError('startup failed')

		class Cleanup(ApplicationCleanup):
			def __call__(self):
				events.append('application-cleanup')

		extension = Lifecycle(events)
		app = Application(
			exts=(extension,),
			on_startup=Startup(),
			on_cleanup=Cleanup(),
		)
		with self.assertRaisesRegex(ValueError, 'startup failed'):
			app.start()
		self.assertFalse(app.running)
		self.assertEqual(app.exts, (extension,))
		self.assertEqual(events, ['application-start'])
		return

	def test_cleanup_attempts_all_extensions_and_marks_application_stopped(self):
		events = []

		class Cleanup(ApplicationCleanup):
			def __call__(self):
				events.append('application-cleanup')
				raise RuntimeError('application cleanup failed')

		app = Application(
			exts=(
				Lifecycle(
					events,
					'/first',
					fail_cleanup=True,
				),
				Lifecycle(
					events,
					'/last',
					fail_cleanup=True,
				),
			),
			on_cleanup=Cleanup(),
		)
		app.start()
		events.clear()
		with self.assertLogs('DefEssential.Application', level='ERROR'):
			with self.assertRaisesRegex(ValueError, '/last'):
				app.stop()
		self.assertFalse(app.running)
		self.assertEqual(events, [
			'extension-cleanup:/last',
			'extension-cleanup:/first',
			'application-cleanup',
		])
		return

	def test_request_and_response_hooks_wrap_request_runner_hooks(self):
		events = []

		class FilterRequest(RequestRunnerRequest):
			def __call__(self, req):
				events.append('runner-request')
				return req

		class FilterResponse(RequestRunnerRequestResponse):
			def __call__(self, req, response):
				events.append('runner-response')
				return response

		class RequestHook(ApplicationRequest):
			def __call__(self, req):
				events.append('application-request')
				return req

		class ResponseHook(ApplicationRequestResponse):
			def __call__(self, req, response):
				events.append('application-response-first')
				return Response(body=b'changed')

		class FinalResponseHook(ApplicationRequestResponse):
			def __call__(self, req, response):
				events.append('application-response-last')
				return Response(body=b'updated')

		class SecondRequestHook(ApplicationRequest):
			def __call__(self, req):
				events.append('application-request-last')
				return req

		class Handler(
			RequestRunner,
			method='GET',
			url='/hook',
			on_request=FilterRequest(),
			on_request_response=FilterResponse(),
		):
			def run(self, req):
				events.append('handler')
				return Response(body=b'original')

		app = Application(
			on_request=(
				RequestHook(),
				SecondRequestHook(),
			),
			on_request_response=(
				ResponseHook(),
				FinalResponseHook(),
			),
		)
		app.add(Handler)
		response = app(request())
		assert isinstance(response, Response)
		self.assertEqual(response.body, b'updated')
		self.assertEqual(events, [
			'application-request',
			'application-request-last',
			'runner-request',
			'handler',
			'runner-response',
			'application-response-first',
			'application-response-last',
		])
		return

	def test_response_hook_accepts_none_after_direct_output(self):
		responses = []

		class ResponseHook(ApplicationRequestResponse):
			def __call__(self, req, response):
				responses.append(response)
				return response

		class Handler(
			RequestRunner,
			method='GET',
			url='/hook',
		):
			def run(self, req):
				req.writer.begin(Response())
				req.writer.write(b'direct')
				return None

		writer = ResponseWriter(
			lambda response, chunked: None,
			BytesIO(),
		)
		app = Application(on_request_response=ResponseHook())
		app.add(Handler)
		self.assertIsNone(app(request(writer=writer)))
		self.assertEqual(responses, [None])
		return

	def test_request_errors_are_observed_and_hook_errors_propagate(self):
		observed = []

		class RequestHook(ApplicationRequest):
			def __call__(self, req):
				raise ValueError('request hook failed')

		class ErrorHook(ApplicationRequestError):
			def __call__(self, req, error):
				observed.append((req, error))

		app = Application(
			on_request=RequestHook(),
			on_request_error=ErrorHook(),
		)
		with self.assertRaisesRegex(ValueError, 'request hook failed'):
			app(request())
		self.assertEqual(len(observed), 1)
		self.assertIsInstance(observed[0][0], Request)
		self.assertIsInstance(observed[0][1], ValueError)

		class FailingErrorHook(ApplicationRequestError):
			def __call__(self, req, error):
				raise RuntimeError('error hook failed')

		app = Application(
			on_request=RequestHook(),
			on_request_error=FailingErrorHook(),
		)
		with self.assertRaisesRegex(RuntimeError, 'error hook failed') as raised:
			app(request())
		self.assertIsInstance(raised.exception.__context__, ValueError)
		return

	def test_application_error_response_stops_hooks_and_does_not_repeat_response_hooks(self):
		events = []
		error = ValueError('response hook failed')
		response = Response(status=503, body=b'application recovery')
		original_body = BytesIO(b'original')

		class ResponseHook(ApplicationRequestResponse):
			def __call__(self, req, result):
				events.append('response')
				raise error

		class ErrorHook(ApplicationRequestError):
			def __init__(self, result):
				self.result = result
				return

			def __call__(self, req, caught):
				events.append('error')
				return self.result

		class Handler(RequestRunner, method='GET', url='/hook'):
			def run(self, req):
				return Response(body=original_body)

		app = Application(
			on_request_response=ResponseHook(),
			on_request_error=(
				ErrorHook(None),
				ErrorHook(response),
				ErrorHook(self.fail),
			),
		)
		app.add(Handler)
		result = app(request())
		self.assertIs(result, response)
		self.assertEqual(events, ['response', 'error', 'error'])
		self.assertTrue(original_body.closed)
		return

	def test_adapter_transmits_application_error_response(self):
		response = Response(status=418, body=b'application error')

		class RequestHook(ApplicationRequest):
			def __call__(self, req):
				raise ValueError('request failed')

		class ErrorHook(ApplicationRequestError):
			def __call__(self, req, error):
				return response

		app = Application(
			on_request=RequestHook(),
			on_request_error=ErrorHook(),
		)
		output = BytesIO()
		writer = ResponseWriter(lambda current, chunked: None, output)
		handle_request(
			app,
			lambda: request(writer=writer),
			writer,
		)
		self.assertEqual(writer.status, 418)
		self.assertEqual(output.getvalue(), b'application error')
		return

	def test_application_error_response_cannot_replace_started_direct_output(self):
		body = BytesIO(b'recovery body')
		response = Response(status=503, body=body)
		writer = ResponseWriter(lambda current, chunked: None, BytesIO())

		class RequestHook(ApplicationRequest):
			def __call__(self, req):
				req.writer.begin(Response(status=202))
				raise ValueError('direct output failed')

		class ErrorHook(ApplicationRequestError):
			def __call__(self, req, error):
				return response

		app = Application(
			on_request=RequestHook(),
			on_request_error=ErrorHook(),
		)
		with self.assertRaisesRegex(RuntimeError, 'starting direct output') as caught:
			app(request(writer=writer))
		self.assertIsInstance(caught.exception.__context__, ValueError)
		self.assertEqual(writer.status, 202)
		self.assertTrue(body.closed)
		return

	def test_route_errors_reach_application_error_hooks(self):
		errors = []

		class ErrorHook(ApplicationRequestError):
			def __call__(self, req, error):
				errors.append(error)

		app = Application(on_request_error=ErrorHook())
		with self.assertRaises(ClientError):
			app(request('/missing'))
		self.assertEqual(len(errors), 1)
		self.assertIsInstance(errors[0], ClientError)
		return

	def test_application_methods_cannot_be_reentered_from_hooks(self):
		application = None

		class RequestHook(ApplicationRequest):
			def __call__(self, req):
				assert application is not None
				return application(req)

		application = Application(on_request=RequestHook())
		with self.assertRaisesRegex(RuntimeError, 'Application methods cannot'):
			application(request())
		return

	def test_lifecycle_methods_cannot_be_reentered_from_startup_hooks(self):
		application = None

		class Startup(ApplicationStartup):
			def __call__(self):
				assert application is not None
				application.start()

		application = Application(on_startup=Startup())
		with self.assertRaisesRegex(RuntimeError, 'Application methods cannot'):
			application.start()
		self.assertFalse(application.running)
		return


if __name__ == '__main__':
	import unittest

	unittest.main()
