from dataclasses import (
	dataclass,
	field,
)
from logging import getLogger
from math import floor
from threading import Lock
from time import monotonic
from typing import (
	Callable,
	Optional,
	Sequence,
	Union,
)
from uuid import uuid4
from weakref import WeakKeyDictionary

from ..Application import (
	Application,
	ApplicationRequest,
	ApplicationRequestError,
	ApplicationRequestResponse,
	RequestHookRegistration,
)
from ..Extension import (
	Extension,
	ExtensionCleanup,
	ExtensionRequest,
	ExtensionRequestError,
	ExtensionRequestResponse,
	ExtensionStartup,
)
from ..Request import Request
from ..Response import Response
from ..Responses import ResponseJSON
from ..Router import Router
from .Utils.Routes import (
	http_routes,
	validate_path,
)

__all__ = (
	'RequestMetrics',
	'Observation',
	'Metrics',
	'MetricsCollector',
)


@dataclass
class RequestMetrics:
	active: int = 0
	success: int = 0
	failure: int = 0
	duration: float = 0
	starts: dict[str, float] = field(default_factory=dict)
	buckets: dict[int, dict[str, float]] = field(default_factory=dict)

	def prune(
		self,
		now: float,
	) -> None:
		for second in tuple(self.buckets):
			if second < floor(now) - 60:
				del self.buckets[second]
		return

	def window(
		self,
		end: int,
		seconds: int,
	) -> dict:
		buckets = [
			bucket for second, bucket in self.buckets.items()
			if end - seconds <= second < end
		]
		return {
			'success': sum(bucket['success'] for bucket in buckets),
			'failure': sum(bucket['failure'] for bucket in buckets),
			'duration': sum(bucket['duration'] for bucket in buckets),
			'max_duration': max(
				(bucket['max_duration'] for bucket in buckets),
				default=0,
			),
		}


@dataclass(frozen=True)
class Observation:
	key: str
	id: str
	started: float


def label(value: str) -> str:
	return value.replace('\\', '\\\\').replace('\n', '\\n').replace('"', '\\"')


class MetricsCollector:
	"""Collect metrics at application processing boundaries.

	A started Metrics instance attaches the collector to application request hooks.
	Transmission time and stream-consumption errors after a response is returned
	are not included.
	"""

	def __init__(
		self,
	):
		self.lock = Lock()
		self.requests: dict[str, RequestMetrics] = {}
		self.started_at: Optional[float] = None
		self.instance = ''
		self.router: Optional[Router] = None
		self.running: Optional[Callable[[], bool]] = None
		self.request_scope: Optional[Callable[[], Optional[Request]]] = None
		self.observations: dict[str, Observation] = {}
		self.completed: WeakKeyDictionary[Request, tuple[Observation, float, int, bool]] = WeakKeyDictionary()
		self.on_request = ObserveRequest(self)
		self.on_request_response = ObserveResponse(self)
		self.on_request_error = ObserveError(self)
		return

	def bind(
		self,
		router: Router,
		running: Callable[[], bool],
		request_scope: Callable[[], Optional[Request]],
	) -> None:
		if self.router is not None and self.router is not router:
			raise ValueError('Use a separate MetricsCollector for each Application')
		self.router = router
		self.running = running
		self.request_scope = request_scope
		return

	def observation_request(
		self,
		request: Request,
	) -> Request:
		"""Associate a replacement Request with the original request in the current application call."""
		if self.request_scope is None:
			raise RuntimeError('MetricsCollector is not bound to an Application request scope')
		current = self.request_scope()
		return request if current is None else current

	def reset(self) -> None:
		with self.lock:
			if self.router is None:
				raise RuntimeError('MetricsCollector is not bound to a router')
			if any(stats.active for stats in self.requests.values()):
				raise RuntimeError('Cannot restart Metrics while requests are still active')
			self.requests = {
				route.method + ' ' + route.url: RequestMetrics()
				for route in self.router.routes
			}
			self.requests['<unmatched>'] = RequestMetrics()
			self.started_at = monotonic()
			self.instance = uuid4().hex
			self.observations.clear()
			self.completed.clear()
		return

	def begin(
		self,
		request: Request,
	) -> Observation:
		if self.router is None:
			raise RuntimeError('MetricsCollector is not bound to a router')
		matches = self.router.matches(request.path)
		match = matches.get(request.method)
		key = request.method + ' ' + match[0].url if match is not None else '<unmatched>'
		with self.lock:
			if self.started_at is None:
				raise RuntimeError('Metrics has not been started')
			context = Observation(
				key,
				self.observation_request(request).id,
				monotonic(),
			)
			if context.id in self.observations:
				raise RuntimeError('Request is already being observed')
			self.observations[context.id] = context
			stats = self.requests.setdefault(key, RequestMetrics())
			stats.active += 1
			stats.starts[context.id] = context.started
		return context

	def end(
		self,
		request: Request,
		status: int,
		error: Optional[Exception],
	) -> None:
		request = self.observation_request(request)
		with self.lock:
			context = self.observations.pop(request.id, None)
			if context is None:
				completed = self.completed.get(request)
				if error is not None and completed is not None and completed[3]:
					observation, duration, second, _ = completed
					stats = self.requests[observation.key]
					stats.success -= 1
					stats.failure += 1
					if second in stats.buckets:
						stats.buckets[second]['success'] -= 1
						stats.buckets[second]['failure'] += 1
					self.completed[request] = (
						observation,
						duration,
						second,
						False,
					)
				return
			stats = self.requests[context.key]
			del stats.starts[context.id]
			stats.active -= 1
			now = monotonic()
			duration = now - context.started
			success = error is None and status < 400
			stats.success += int(success)
			stats.failure += int(not success)
			stats.duration += duration
			stats.prune(now)
			bucket = stats.buckets.setdefault(
				floor(now),
				{
					'success': 0,
					'failure': 0,
					'duration': 0,
					'max_duration': 0,
				},
			)
			bucket['success'] += int(success)
			bucket['failure'] += int(not success)
			bucket['duration'] += duration
			bucket['max_duration'] = max(bucket['max_duration'], duration)
			self.completed[request] = (
				context,
				duration,
				floor(now),
				success,
			)
		return

	def snapshot(
		self,
	) -> dict:
		with self.lock:
			if self.started_at is None or self.running is None or self.router is None:
				raise RuntimeError('Metrics has not been started')
			now = monotonic()
			for stats in self.requests.values():
				stats.prune(now)
			for route in self.router.routes:
				self.requests.setdefault(route.method + ' ' + route.url, RequestMetrics())
			return {
				'instance': self.instance,
				'sampled_at': now,
				'uptime': now - self.started_at,
				'running': self.running(),
				'window_end': floor(now),
				'requests': {
					key: {
						'active': stats.active,
						'success': stats.success,
						'failure': stats.failure,
						'duration': stats.duration,
						'oldest_active': now - min(stats.starts.values()) if stats.starts else 0,
						'windows': {
							str(seconds): stats.window(
								floor(now),
								seconds,
							)
							for seconds in (
								1,
								60,
							)
						},
					}
					for key, stats in self.requests.items()
				},
			}

	def render(
		self,
	) -> str:
		snapshot = self.snapshot()
		lines = [
			'# HELP defchord_application_running Application lifecycle is running; not an external heartbeat.',
			'# TYPE defchord_application_running gauge',
			f'defchord_application_running {int(snapshot["running"])}',
			'# HELP defchord_application_uptime_seconds Seconds since application startup.',
			'# TYPE defchord_application_uptime_seconds gauge',
			f'defchord_application_uptime_seconds {snapshot["uptime"]}',
			'# HELP defchord_requests_active Requests being processed by the Application.',
			'# TYPE defchord_requests_active gauge',
			'# HELP defchord_requests_total Completed Application requests by outcome.',
			'# TYPE defchord_requests_total counter',
			'# HELP defchord_request_duration_seconds Application processing duration; excludes response transfer.',
			'# TYPE defchord_request_duration_seconds summary',
			'# TYPE defchord_request_oldest_active_seconds gauge',
			'# TYPE defchord_requests_window gauge',
			'# TYPE defchord_request_window_duration_seconds_sum gauge',
			'# TYPE defchord_request_window_duration_seconds_max gauge',
		]
		for key, stats in snapshot['requests'].items():
			tags = 'route="' + label(key) + '"'
			lines.extend((
				f'defchord_requests_active{{{tags}}} {stats["active"]}',
				f'defchord_requests_total{{{tags},outcome="success"}} {stats["success"]}',
				f'defchord_requests_total{{{tags},outcome="failure"}} {stats["failure"]}',
				f'defchord_request_duration_seconds_count{{{tags}}} {stats["success"] + stats["failure"]}',
				f'defchord_request_duration_seconds_sum{{{tags}}} {stats["duration"]}',
				f'defchord_request_oldest_active_seconds{{{tags}}} {stats["oldest_active"]}',
			))
			for seconds, window in stats['windows'].items():
				window_tags = tags + ',window_seconds="' + seconds + '"'
				lines.extend((
					f'defchord_requests_window{{{window_tags},outcome="success"}} {window["success"]}',
					f'defchord_requests_window{{{window_tags},outcome="failure"}} {window["failure"]}',
					f'defchord_request_window_duration_seconds_sum{{{window_tags}}} {window["duration"]}',
					f'defchord_request_window_duration_seconds_max{{{window_tags}}} {window["max_duration"]}',
				))
		return '\n'.join(lines) + '\n'



class ObserveRequest(ApplicationRequest):
	"""Forward application request entry to the shared collector."""

	def __init__(
		self,
		collector: MetricsCollector,
	):
		self.collector = collector
		return

	def __call__(
		self,
		request: Request,
	) -> Request:
		self.collector.begin(request)
		return request


class ObserveResponse(ApplicationRequestResponse):
	"""Collect the state of a returned response or direct-output writer."""

	def __init__(
		self,
		collector: MetricsCollector,
	):
		self.collector = collector
		return

	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		status = response.status if response is not None else request.writer.status
		self.collector.end(
			request,
			status,
			None,
		)
		return response


class ObserveError(ApplicationRequestError):
	"""Collect failures, including post-response-hook errors, without double-counting completions."""

	def __init__(
		self,
		collector: MetricsCollector,
	):
		self.collector = collector
		return

	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> None:
		self.collector.end(
			request,
			500,
			error,
		)
		return


class Metrics(Extension):
	"""Observe all application requests and expose metrics as JSON or Prometheus."""

	logger = getLogger('Extension.Metrics')

	def __init__(
		self,
		path: str,
		*,
		collector: Optional[MetricsCollector] = None,
		on_startup: Optional[Union[
			ExtensionStartup,
			Sequence[ExtensionStartup],
		]] = None,
		on_cleanup: Optional[Union[
			ExtensionCleanup,
			Sequence[ExtensionCleanup],
		]] = None,
		on_request: Optional[Union[
			ExtensionRequest,
			Sequence[ExtensionRequest],
		]] = None,
		on_request_response: Optional[Union[
			ExtensionRequestResponse,
			Sequence[ExtensionRequestResponse],
		]] = None,
		on_request_error: Optional[Union[
			ExtensionRequestError,
			Sequence[ExtensionRequestError],
		]] = None,
	):
		super().__init__(
			on_startup=on_startup,
			on_cleanup=on_cleanup,
			on_request=on_request,
			on_request_response=on_request_response,
			on_request_error=on_request_error,
		)
		validate_path(path)
		self.path = path
		self.collector = MetricsCollector() if collector is None else collector
		self.hook_token: Optional[RequestHookRegistration] = None
		return

	def __str__(self) -> str:
		return '{}({})'.format(type(self).__name__, self.path)

	def startup(
		self,
		application: Application,
	) -> None:
		self.application = application
		self.collector.bind(
			application.router,
			lambda: application.running,
			lambda: getattr(application.hook_context, 'request', None),
		)
		self.collector.reset()
		self.logger.debug('Metrics initialized: routes=%s', len(application.router.routes))
		for route in http_routes(self, self.path):
			application.add_extension_route(self, route)
		self.hook_token = application.add_request_hooks(
			on_request=self.collector.on_request,
			on_request_response=self.collector.on_request_response,
			on_request_error=self.collector.on_request_error,
		)
		self.logger.debug('Metrics observation hooks connected')
		try:
			super().startup(application)
		except Exception:
			try:
				application.remove_request_hooks(self.hook_token)
			except Exception:
				self.logger.exception('시작 실패 후 요청 훅 해제에 실패했습니다')
			finally:
				self.hook_token = None
			raise
		return

	def cleanup(self) -> None:
		error = None
		try:
			if self.hook_token is not None:
				self.application.remove_request_hooks(self.hook_token)
				self.logger.debug('Metrics observation hooks disconnected')
		except Exception as caught:
			error = caught
		finally:
			self.hook_token = None
		try:
			super().cleanup()
		except Exception:
			if error is None:
				raise
			self.logger.exception('요청 훅 해제 실패 후 사용자 정리에 실패했습니다')
		if error is not None:
			raise error
		return

	def __call__(
		self,
		request: Request,
	) -> Response:
		if request.header('Accept') == 'application/json':
			self.logger.debug('Metrics snapshot preparing: request_id=%s', request.id)
			response = ResponseJSON(
				self.collector.snapshot(),
				headers={'Cache-Control': 'no-store'},
			)
		else:
			self.logger.debug('Metrics text rendering: request_id=%s', request.id)
			response = Response(
				body=self.collector.render().encode('utf-8'),
				format='text/plain; version=0.0.4',
				charset='utf-8',
			)
		self.logger.debug('Metrics response prepared: request_id=%s', request.id)
		return response
