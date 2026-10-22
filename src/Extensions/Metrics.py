from dataclasses import (
	dataclass,
	field,
)
from math import floor
from threading import Lock
from time import monotonic
from typing import Optional
from uuid import uuid4

from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..Response import Response

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


class Metrics(Extension):
	"""Collect thread-safe Prometheus metrics through HTTP transmission completion."""

	def __init__(
		self,
		path: str,
	):
		super().__init__(path)
		self.lock = Lock()
		self.requests: dict[str, RequestMetrics] = {}
		self.started_at: Optional[float] = None
		self.instance = ''
		return

	def start(
		self,
		app: Application,
	) -> None:
		with self.lock:
			if any(stats.active for stats in self.requests.values()):
				raise RuntimeError('Cannot restart Metrics while requests are still active')
			self.requests = {
				route.method + ' ' + route.url: RequestMetrics()
				for route in app.router.routes
			}
			self.requests['<unmatched>'] = RequestMetrics()
			self.started_at = monotonic()
			self.instance = uuid4().hex
		return

	def begin(
		self,
		request: Request,
	) -> Observation:
		app = self.application
		if app is None:
			raise RuntimeError('Metrics is not bound to an Application')
		matches = app.router.matches(request.path)
		match = matches.get(request.method)
		key = request.method + ' ' + match[0].url if match is not None else '<unmatched>'
		with self.lock:
			if self.started_at is None:
				raise RuntimeError('Metrics has not been started')
			context = Observation(
				key,
				request.id,
				monotonic(),
			)
			stats = self.requests[key]
			stats.active += 1
			stats.starts[context.id] = context.started
		return context

	def end(
		self,
		request: Request,
		context: object,
		status: int,
		error: Optional[BaseException],
	) -> None:
		if not isinstance(context, Observation):
			raise TypeError('An Observation created by Metrics is required')
		with self.lock:
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
		return

	def snapshot(
		self,
		app: Application,
	) -> dict:
		with self.lock:
			if self.started_at is None:
				raise RuntimeError('Metrics has not been started')
			now = monotonic()
			for stats in self.requests.values():
				stats.prune(now)
			return {
				'instance': self.instance,
				'sampled_at': now,
				'uptime': now - self.started_at,
				'running': app.running,
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
		app: Application,
	) -> str:
		snapshot = self.snapshot(app)
		lines = [
			'# HELP defessential_application_running Application lifecycle is running; not an external heartbeat.',
			'# TYPE defessential_application_running gauge',
			f'defessential_application_running {int(snapshot["running"])}',
			'# HELP defessential_application_uptime_seconds Seconds since application startup.',
			'# TYPE defessential_application_uptime_seconds gauge',
			f'defessential_application_uptime_seconds {snapshot["uptime"]}',
			'# HELP defessential_requests_active Requests whose response transfer has not completed.',
			'# TYPE defessential_requests_active gauge',
			'# HELP defessential_requests_total Completed HTTP requests by outcome.',
			'# TYPE defessential_requests_total counter',
			'# HELP defessential_request_duration_seconds Duration through response transfer.',
			'# TYPE defessential_request_duration_seconds summary',
			'# TYPE defessential_request_oldest_active_seconds gauge',
			'# TYPE defessential_requests_window gauge',
			'# TYPE defessential_request_window_duration_seconds_sum gauge',
			'# TYPE defessential_request_window_duration_seconds_max gauge',
		]
		for key, stats in snapshot['requests'].items():
			tags = 'route="' + label(key) + '"'
			lines.extend((
				f'defessential_requests_active{{{tags}}} {stats["active"]}',
				f'defessential_requests_total{{{tags},outcome="success"}} {stats["success"]}',
				f'defessential_requests_total{{{tags},outcome="failure"}} {stats["failure"]}',
				f'defessential_request_duration_seconds_count{{{tags}}} {stats["success"] + stats["failure"]}',
				f'defessential_request_duration_seconds_sum{{{tags}}} {stats["duration"]}',
				f'defessential_request_oldest_active_seconds{{{tags}}} {stats["oldest_active"]}',
			))
			for seconds, window in stats['windows'].items():
				window_tags = tags + ',window_seconds="' + seconds + '"'
				lines.extend((
					f'defessential_requests_window{{{window_tags},outcome="success"}} {window["success"]}',
					f'defessential_requests_window{{{window_tags},outcome="failure"}} {window["failure"]}',
					f'defessential_request_window_duration_seconds_sum{{{window_tags}}} {window["duration"]}',
					f'defessential_request_window_duration_seconds_max{{{window_tags}}} {window["max_duration"]}',
				))
		return '\n'.join(lines) + '\n'

	def handle(
		self,
		app: Application,
		request: Request,
	) -> Response:
		return Response(
			body=self.render(app).encode('utf-8'),
			format='text/plain; version=0.0.4',
			charset='utf-8',
		)
