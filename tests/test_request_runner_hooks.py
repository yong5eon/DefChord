from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from io import BytesIO
from threading import Barrier
from unittest import TestCase

from DefEssential import (
	Application,
	ApplicationRequest,
	ApplicationRequestError,
	ApplicationRequestResponse,
	Auth,
	Body,
	ClientError,
	Extension,
	ExtensionRequestError,
	ExtensionRequestResponse,
	Headers,
	Origin,
	Parameters,
	QueryString,
	Request,
	RequestReader,
	RequestRunner,
	RequestRunnerRequest,
	RequestRunnerRequestError,
	RequestRunnerRequestResponse,
	Response,
	ResponseWriter,
)
from DefEssential.Adapter.RequestHandler import handle_request
from DefEssential.IO.Readers import (
	ChunkedStreamContentReader,
	StreamContentReader,
)
from DefEssential.IO.Writers import (
	ChunkedStreamWriter,
	ServerSentEventsWriter,
	StreamWriter,
)
from DefEssential.Runners.RunExtension import run_extension
from DefEssential.Runners.RunRequest import RunRequest


class RequestHook(RequestRunnerRequest):
	def __init__(
		self,
		callback,
	):
		self.callback = callback
		return

	def __call__(
		self,
		request,
	):
		return self.callback(request)


class ResponseHook(RequestRunnerRequestResponse):
	def __init__(
		self,
		callback,
	):
		self.callback = callback
		return

	def __call__(
		self,
		request,
		response,
	):
		return self.callback(request, response)


class ErrorHook(RequestRunnerRequestError):
	def __init__(
		self,
		callback,
	):
		self.callback = callback
		return

	def __call__(
		self,
		request,
		error,
	):
		return self.callback(request, error)


class TrackedBody:
	def __init__(
		self,
		fail=False,
	):
		self.closes = 0
		self.iterations = 0
		self.fail = fail
		return

	def __iter__(self):
		self.iterations += 1
		yield b'body'

	def close(self):
		self.closes += 1
		if self.fail:
			raise OSError('정리 실패')
		return


def request(writer=None):
	return Request(
		'127.0.0.1',
		1,
		'GET',
		'/',
		writer=writer,
	)


def handler(
	callback,
	**settings,
):
	class Handler(
		RequestRunner,
		method='GET',
		url='/',
		**settings,
	):
		def run(
			self,
			request,
		):
			return callback(request)

	return Handler


class RequestRunnerHookTests(TestCase):
	def test_exports_and_removed_api(self):
		for module in (
			import_module('DefEssential'),
			import_module('DefEssential.RequestRunner'),
		):
			for contract in (
				RequestRunnerRequest,
				RequestRunnerRequestResponse,
				RequestRunnerRequestError,
			):
				self.assertIs(getattr(module, contract.__name__), contract)
				self.assertIn(contract.__name__, module.__all__)
			for name in (
				'RequestFilter',
				'ResponseFilter',
			):
				self.assertFalse(hasattr(module, name))
		for keyword in (
			'onRequest',
			'onResponse',
			'on_response',
			'on_error',
		):
			with self.subTest(keyword=keyword), self.assertRaises(TypeError):
				handler(lambda req: Response(), **{keyword: None})
		return

	def test_configuration_normalization_copy_and_inheritance(self):
		for name, contract in (
			('on_request', RequestHook(lambda req: req)),
			('on_request_response', ResponseHook(lambda req, response: response)),
			('on_request_error', ErrorHook(lambda req, error: None)),
		):
			with self.subTest(name=name):
				for value in (
					None,
					(),
					[],
				):
					base = handler(lambda req: Response(), **{name: value})
					self.assertEqual(getattr(base.properties, name), ())
				hooks = [contract]
				base = handler(lambda req: Response(), **{name: hooks})
				hooks.clear()
				self.assertEqual(getattr(base.properties, name), (contract,))
				single = handler(lambda req: Response(), **{name: contract})
				self.assertEqual(getattr(single.properties, name), (contract,))

				class Child(base):
					pass

				class Reused(base, **{name: getattr(base.properties, name)}):
					pass

				self.assertEqual(getattr(Child.properties, name), ())
				self.assertEqual(getattr(Reused.properties, name), (contract,))
				for invalid in (
					'text',
					b'bytes',
					object(),
					type(contract),
					lambda: None,
					[contract, object()],
					iter([contract]),
				):
					with self.assertRaises(TypeError):
						handler(lambda req: Response(), **{name: invalid})
		return

	def test_validation_constructor_and_hook_order(self):
		events = []

		def check_type(
			contract,
			label,
		):
			class Check(contract):
				def __init__(self):
					return

				def __call__(
					self,
					req,
				):
					events.append(label)
					return 'body'

			return Check()

		def before(req):
			self.assertEqual(req.body, 'body')
			events.append('request')
			return req

		def after(
			req,
			response,
		):
			events.append('response')
			return response

		base = handler(
			lambda req: events.append('run') or Response(),
			origin=Origin(all=True),
			auth=check_type(Auth, 'auth'),
			parameters=check_type(Parameters, 'parameters'),
			qs=check_type(QueryString, 'query'),
			headers=check_type(Headers, 'headers'),
			body=check_type(Body, 'body'),
			on_request=RequestHook(before),
			on_request_response=ResponseHook(after),
		)

		class Handler(
			base,
			**{
				key: getattr(base.properties, key)
				for key in (
					'auth',
					'parameters',
					'qs',
					'headers',
					'body',
					'on_request',
					'on_request_response',
				)
			},
		):
			def __init__(self):
				events.append('constructor')
				return

		RunRequest(Handler).run(request())
		self.assertEqual(events, [
			'auth',
			'parameters',
			'query',
			'headers',
			'body',
			'constructor',
			'request',
			'run',
			'response',
		])
		return

	def test_request_replacement_reaches_run_and_writer_callback(self):
		seen = []
		original = request()
		output = BytesIO()
		writer = ResponseWriter(
			lambda response, chunked: seen.append(response.header('X-Request')),
			output,
		)
		replacement = request(writer)
		replacement.body = 'prepared'

		def run(req):
			self.assertIs(req, replacement)
			self.assertEqual(req.body, 'prepared')
			req.writer.begin(Response())
			req.writer.write(b'data')
			return

		def after(
			req,
			response,
		):
			self.assertIs(req, replacement)
			response.header('X-Request', req.id)
			return response

		runner = handler(
			run,
			on_request=(
				RequestHook(lambda req: replacement),
				RequestHook(lambda req: seen.append(req) or req),
			),
			on_request_response=ResponseHook(after),
		)
		self.assertIsNone(RunRequest(runner).run(original))
		self.assertEqual(seen, [
			replacement,
			replacement.id,
		])
		self.assertIsNone(writer.on_request_response)
		return

	def test_failure_stages_notify_once_and_stop_normal_hooks(self):
		for stage in (
			'origin',
			'auth',
			'parameters',
			'qs',
			'headers',
			'body',
			'constructor',
			'request',
			'run',
			'response',
			'cors',
		):
			with self.subTest(stage=stage):
				error = ValueError(stage)
				events = []

				def fail(*args):
					raise error

				settings = {
					'on_request': RequestHook(fail if stage == 'request' else lambda req: req),
					'on_request_response': (
						ResponseHook(fail if stage == 'response' else lambda req, response: response),
						ResponseHook(lambda req, response: events.append('response') or response),
					),
					'on_request_error': ErrorHook(lambda req, caught: events.append((req, caught))),
				}
				contracts = {
					'auth': Auth,
					'parameters': Parameters,
					'qs': QueryString,
					'headers': Headers,
					'body': Body,
				}
				if stage in contracts:
					class Broken(contracts[stage]):
						def __init__(self):
							return

						def __call__(
							self,
							req,
						):
							raise error

					settings[stage] = Broken()
				base = handler(
					fail if stage == 'run' else lambda req: Response(),
					**settings,
				)
				if stage == 'constructor':
					class BrokenConstructor(base, **settings):
						def __init__(self):
							raise error

					base = BrokenConstructor
				execution = RunRequest(base)
				if stage == 'origin':
					def fail_origin(request: Request) -> None:
						raise error

					execution.cross_origin_resource_sharing.validate_origin = fail_origin
				if stage == 'cors':
					def fail_cors(
						request: Request,
						response: Response,
						*,
						preflight: bool = False,
					) -> Response:
						raise error

					execution.cross_origin_resource_sharing.apply_to_response = fail_cors
				req = request()
				with self.assertRaises(ValueError) as caught:
					execution.run(req)
				self.assertIs(caught.exception, error)
				self.assertEqual(events[-1], (req, error))
				self.assertEqual(sum(isinstance(event, tuple) for event in events), 1)
				self.assertEqual('response' in events, stage == 'cors')
		return

	def test_invalid_request_preserves_last_valid_request(self):
		first = request()
		last = request()
		seen = []
		runner = handler(
			lambda req: self.fail('run을 호출하면 안 됩니다'),
			on_request=(
				RequestHook(lambda req: last),
				RequestHook(lambda req: (req, Response())),
				RequestHook(lambda req: self.fail('후속 훅을 호출하면 안 됩니다')),
			),
			on_request_error=ErrorHook(lambda req, error: seen.append(req)),
		)
		with self.assertRaises(TypeError):
			RunRequest(runner).run(first)
		self.assertEqual(seen, [last])
		return

	def test_error_hook_failure_preserves_chain_and_stops(self):
		for invalid_return in (
			False,
			True,
		):
			error = ValueError('처리 실패')
			hook_error = RuntimeError('오류 훅 실패')
			seen = []

			def fail(req):
				raise error

			def observe(
				req,
				caught,
			):
				seen.append(caught)
				if invalid_return:
					return Response()
				raise hook_error

			runner = handler(
				fail,
				on_request_error=(
					ErrorHook(observe),
					ErrorHook(lambda req, error: self.fail('후속 오류 훅 실행')),
				),
			)
			with self.assertRaises(TypeError if invalid_return else RuntimeError) as caught:
				RunRequest(runner).run(request())
			self.assertIs(caught.exception.__context__, error)
			self.assertEqual(seen, [error])
		return

	def test_response_replacement_and_body_ownership(self):
		for mode in (
			'replace',
			'mutate',
			'share',
			'invalid',
			'raise',
			'cors',
		):
			with self.subTest(mode=mode):
				old = TrackedBody()
				new = TrackedBody()
				response = Response(body=old)

				def after(
					req,
					current,
				):
					if mode == 'replace':
						return Response(body=new)
					if mode == 'mutate':
						current.body = new
					if mode == 'share':
						return Response(body=old)
					if mode == 'invalid':
						return None
					if mode == 'raise':
						current.body = new
						raise ValueError('응답 훅 실패')
					return current

				execution = RunRequest(handler(
					lambda req: response,
					on_request_response=ResponseHook(after),
				))
				if mode == 'cors':
					def fail(
						request: Request,
						response: Response,
						*,
						preflight: bool = False,
					) -> Response:
						raise ValueError('CORS 실패')

					execution.cross_origin_resource_sharing.apply_to_response = fail
				if mode in (
					'invalid',
					'raise',
					'cors',
				):
					with self.assertRaises((TypeError, ValueError)):
						execution.run(request())
					self.assertEqual(old.closes, 1)
					self.assertEqual(new.closes, int(mode == 'raise'))
				else:
					result = execution.run(request())
					assert isinstance(result, Response)
					self.assertEqual(old.closes, int(mode != 'share'))
					self.assertEqual(new.closes, 0)
					self.assertEqual(old.iterations + new.iterations, 0)
					result.close()
					self.assertEqual(old.closes, 1)
					self.assertEqual(new.closes, int(mode != 'share'))
		return

	def test_cleanup_failure_policy(self):
		original = ValueError('처리 실패')
		body = TrackedBody(fail=True)

		def fail(
			req,
			response,
		):
			raise original

		execution = RunRequest(handler(
			lambda req: Response(body=body),
			on_request_response=ResponseHook(fail),
		))
		with self.assertLogs('DefEssential.RequestRunner', level='ERROR'):
			with self.assertRaises(ValueError) as caught:
				execution.run(request())
		self.assertIs(caught.exception, original)
		self.assertEqual(body.closes, 1)
		seen = []
		execution = RunRequest(handler(
			lambda req: Response(body=TrackedBody(fail=True)),
			on_request_response=ResponseHook(lambda req, response: Response()),
			on_request_error=ErrorHook(lambda req, error: seen.append(error)),
		))
		with self.assertRaises(OSError):
			execution.run(request())
		self.assertEqual(len(seen), 1)
		return

	def test_mutated_replaced_bodies_are_all_closed_after_cleanup_failure(self):
		old = TrackedBody(fail=True)
		intermediate = TrackedBody()
		final = TrackedBody()
		seen = []

		def after(
			req,
			response,
		):
			response.body = intermediate
			return Response(body=final)

		execution = RunRequest(handler(
			lambda req: Response(body=old),
			on_request_response=ResponseHook(after),
			on_request_error=ErrorHook(lambda req, error: seen.append(error)),
		))
		with self.assertRaises(OSError):
			execution.run(request())
		for body in (
			old,
			intermediate,
			final,
		):
			self.assertEqual(body.closes, 1)
		self.assertEqual(len(seen), 1)
		return

	def test_stream_begin_precedes_body_and_calls_once(self):
		for mode in (
			'plain',
			'chunked',
			'sse',
			'upgrade',
			'returned',
		):
			with self.subTest(mode=mode):
				events = []

				class Output(BytesIO):
					def write(
						self,
						data,
					):
						events.append('body')
						return super().write(data)

				def send(
					response,
					chunked,
				):
					events.append('headers')
					self.assertEqual(response.header('X-Hook'), 'yes')
					self.assertEqual(response.header('Access-Control-Allow-Origin'), 'https://client')
					if mode == 'upgrade':
						self.assertEqual(response.status, 101)
					return

				writer = ResponseWriter(send, Output())
				req = request(writer)
				req.header('Origin', 'https://client')

				def run(req):
					events.append('run')
					if mode == 'returned':
						return Response(body=b'data')
					if mode == 'upgrade':
						req.writer.upgrade(Response(status=101))
						req.writer.write(b'frame')
					elif mode == 'sse':
						stream = ServerSentEventsWriter(req.writer)
						stream.begin()
						stream.emit('data')
						stream.emit('more')
					else:
						stream = ChunkedStreamWriter(req.writer) if mode == 'chunked' else StreamWriter(req.writer)
						stream.begin()
						stream.write(b'data')
						stream.write(b'more')
					events.append('run-end')
					return

				def after(
					req,
					response,
				):
					events.append('hook')
					self.assertFalse(writer.started)
					response.header('X-Hook', 'yes')
					return response

				runner = handler(
					run,
					origin=Origin(all=True),
					on_request_response=ResponseHook(after),
				)
				response = RunRequest(runner).run(req)
				self.assertIsNone(writer.on_request_response)
				if response is not None:
					writer.response(response, filtered=True)
				self.assertEqual(events.count('hook'), 1)
				self.assertLess(events.index('hook'), events.index('headers'))
				self.assertLess(events.index('headers'), events.index('body'))
				if mode != 'returned':
					self.assertLess(events.index('hook'), events.index('run-end'))
		return

	def test_callback_is_removed_before_server_error_response(self):
		for fail_in_hook in (
			False,
			True,
		):
			events = []
			writer = ResponseWriter(
				lambda response, chunked: events.append(response.status),
				BytesIO(),
			)

			def run(req):
				if not fail_in_hook:
					raise ClientError('거부', status=403)
				req.writer.begin(Response())
				return

			def after(
				req,
				response,
			):
				events.append('hook')
				raise ClientError('응답 훅 거부', status=403)

			app = Application()
			app.add(handler(
				run,
				on_request_response=ResponseHook(after),
			))
			handle_request(app, lambda: request(writer), writer)
			self.assertEqual(events, ['hook', 403] if fail_in_hook else [403])
			self.assertIsNone(writer.on_request_response)
		return

	def test_direct_output_failures_and_conflicting_return(self):
		for stage in (
			'headers',
			'write',
			'flush',
			'conflict',
		):
			with self.subTest(stage=stage):
				events = []
				body = TrackedBody()
				error = OSError(stage)

				class Output(BytesIO):
					def write(
						self,
						data,
					):
						if stage == 'write':
							raise error
						return super().write(data)

					def flush(self):
						if stage == 'flush':
							raise error
						return super().flush()

				def send(
					response,
					chunked,
				):
					if stage == 'headers':
						raise error
					return

				writer = ResponseWriter(send, Output())

				def run(req):
					req.writer.begin(Response())
					req.writer.write(b'data')
					if stage == 'conflict':
						return Response(body=body)
					return

				execution = RunRequest(handler(
					run,
					on_request_response=ResponseHook(lambda req, response: events.append('response') or response),
					on_request_error=ErrorHook(lambda req, error: events.append(error)),
				))
				with self.assertRaises(RuntimeError if stage == 'conflict' else OSError):
					execution.run(request(writer))
				self.assertEqual(events[0], 'response')
				self.assertEqual(len(events), 2)
				if stage != 'conflict':
					self.assertIs(events[1], error)
				self.assertEqual(body.closes, int(stage == 'conflict'))
				self.assertIsNone(writer.on_request_response)
		return

	def test_direct_invalid_body_is_closed(self):
		body = TrackedBody()
		writer = ResponseWriter(lambda response, chunked: None, BytesIO())
		execution = RunRequest(handler(
			lambda req: req.writer.begin(Response()),
			on_request_response=ResponseHook(lambda req, response: Response(body=body)),
		))
		with self.assertRaises(ValueError):
			execution.run(request(writer))
		self.assertEqual(body.closes, 1)
		self.assertFalse(writer.started)
		return

	def test_returned_stream_consumption_failure_is_outside_boundary(self):
		events = []

		def body():
			events.append('consume')
			yield b'body'
			raise OSError('본문 전송 실패')

		writer = ResponseWriter(lambda response, chunked: None, BytesIO())
		app = Application()
		app.add(handler(
			lambda req: Response(body=body()),
			on_request_response=ResponseHook(lambda req, response: events.append('response') or response),
			on_request_error=ErrorHook(lambda req, error: events.append('error')),
		))
		with self.assertLogs('DefEssential.Server', level='WARNING'):
			with self.assertRaises(OSError):
				handle_request(app, lambda: request(writer), writer)
		self.assertEqual(events, [
			'response',
			'consume',
		])
		self.assertIsNone(writer.on_request_response)
		return

	def test_stream_input_is_read_after_request_hook(self):
		for chunked in (
			False,
			True,
		):
			events = []

			class Input(BytesIO):
				def read(
					self,
					size=-1,
				):
					events.append('read')
					return super().read(size)

			req = request()
			req.header('Content-Type', 'application/octet-stream')
			req.reader = RequestReader(
				Input(b'3\r\nabc\r\n0\r\n\r\n' if chunked else b'abc'),
				chunked=chunked,
				size=None if chunked else 3,
			)

			def run(req):
				events.append('run')
				data = req.body.chunk(3) if chunked else req.body.read(3)
				return Response(body=data)

			execution = RunRequest(handler(
				run,
				body=Body(ChunkedStreamContentReader() if chunked else StreamContentReader()),
				on_request=RequestHook(lambda req: events.append('request') or req),
			))
			result = execution.run(req)
			assert isinstance(result, Response)
			self.assertEqual(result.body, b'abc')
			self.assertEqual(events[:2], [
				'request',
				'run',
			])
			self.assertIn('read', events[2:])
		return

	def test_application_boundary_and_extension_order(self):
		for direct in (
			False,
			True,
		):
			events = []

			class AppRequest(ApplicationRequest):
				def __call__(
					self,
					req,
				):
					events.append('app-request')
					return req

			class AppResponse(ApplicationRequestResponse):
				def __call__(
					self,
					req,
					response,
				):
					events.append('app-response')
					return response

			class ExtResponse(ExtensionRequestResponse):
				def __call__(
					self,
					req,
					response,
				):
					events.append('extension-response')
					return response

			class Sample(Extension):
				def __call__(
					self,
					req,
				):
					events.append('extension')
					if direct:
						req.writer.begin(Response())
						req.writer.write(b'data')
						return
					return Response()

			extension = Sample(on_request_response=ExtResponse())
			runner = handler(
				lambda req: run_extension(extension, req),
				on_request=RequestHook(lambda req: events.append('runner-request') or req),
				on_request_response=ResponseHook(lambda req, response: events.append('runner-response') or response),
			)
			app = Application(
				on_request=AppRequest(),
				on_request_response=AppResponse(),
			)
			app.add(runner)
			app(request(ResponseWriter(lambda response, chunked: None, BytesIO())))
			expected = [
				'app-request',
				'runner-request',
				'extension',
				'runner-response' if direct else 'extension-response',
				'extension-response' if direct else 'runner-response',
				'app-response',
			]
			self.assertEqual(events, expected)
		return

	def test_pre_dispatch_failure_does_not_enter_runner(self):
		events = []

		class AppError(ApplicationRequestError):
			def __call__(
				self,
				req,
				error,
			):
				events.append('app-error')
				return

		app = Application(on_request_error=AppError())
		app.add(handler(
			lambda req: Response(),
			on_request=RequestHook(lambda req: events.append('request') or req),
			on_request_error=ErrorHook(lambda req, error: events.append('error')),
		))
		req = request()
		req.uri = '/missing'
		req.path = '/missing'
		with self.assertRaises(ClientError):
			app(req)
		req = request()
		req.reader = RequestReader(BytesIO(b'data'), size=4)
		with self.assertRaises(ClientError):
			app(req)
		self.assertEqual(events, [
			'app-error',
			'app-error',
		])
		return

	def test_extension_and_runner_errors_propagate_in_boundary_order(self):
		for direct in (
			False,
			True,
		):
			events = []
			error = ValueError('확장 실행 실패')

			class AppError(ApplicationRequestError):
				def __call__(
					self,
					req,
					caught,
				):
					events.append(('application', caught))
					return

			class ExtError(ExtensionRequestError):
				def __call__(
					self,
					req,
					caught,
				):
					events.append(('extension', caught))
					return

			class Sample(Extension):
				def __call__(
					self,
					req,
				):
					if direct:
						req.writer.begin(Response())
						return
					raise error

			def after(
				req,
				response,
			):
				raise error

			extension = Sample(on_request_error=ExtError())
			app = Application(on_request_error=AppError())
			app.add(handler(
				lambda req: run_extension(extension, req),
				on_request_response=ResponseHook(after),
				on_request_error=ErrorHook(lambda req, caught: events.append(('runner', caught))),
			))
			writer = ResponseWriter(lambda response, chunked: None, BytesIO())
			with self.assertRaises(ValueError) as caught:
				app(request(writer))
			self.assertIs(caught.exception, error)
			self.assertEqual(events, [
				('extension', error),
				('runner', error),
				('application', error),
			])
			self.assertIsNone(writer.on_request_response)
		return

	def test_concurrent_requests_share_hooks_not_callback_state(self):
		barrier = Barrier(2)
		seen = []
		hook = ResponseHook(lambda req, response: response.header('X-Request', req.id) or response)

		def run(req):
			barrier.wait(timeout=5)
			req.writer.begin(Response())
			return

		runner = handler(run, on_request_response=hook)
		apps = (
			Application(),
			Application(),
		)
		for app in apps:
			app.add(runner)
		self.assertIs(runner.properties.on_request_response[0], hook)

		def invoke(app):
			sent = []
			writer = ResponseWriter(lambda response, chunked: sent.append(response), BytesIO())
			req = request(writer)
			app(req)
			self.assertEqual(sent[0].header('X-Request'), req.id)
			self.assertIsNone(writer.on_request_response)
			return req.id

		with ThreadPoolExecutor(max_workers=2) as executor:
			seen = list(executor.map(invoke, apps))
		self.assertEqual(len(set(seen)), 2)
		return
