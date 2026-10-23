from os import name
from typing import (
	Any,
	Union,
)

from ....Application import Application
from ....Startup import startup
from ...Server import Server as ServerAdapter
from .Transport import (
	Body,
	GunicornApplication as RequestApplication,
)

__all__ = (
	'Server',
)


class Server(ServerAdapter):
	"""Gunicorn의 워커별로 애플리케이션을 시작하고 종료한다."""

	def __init__(
		self,
		host: str,
		port: int,
		application: Application,
		*,
		workers: int = 1,
		worker_class: Union[str, type] = 'sync',
		**options: Any,
	):
		super().__init__(
			host,
			port,
			application,
		)
		if workers < 1:
			raise ValueError('workers must be at least 1')
		if 'bind' in options:
			raise ValueError('Use host and port instead of bind')
		self.workers = workers
		self.worker_class = worker_class
		self.options = options
		return

	def run(self) -> None:
		if name == 'nt':
			raise RuntimeError('Gunicorn requires a POSIX platform; use Linux or WSL')
		# Gunicorn은 선택적 의존성이며 Windows에서는 가져올 수 없다.
		from gunicorn.app.base import BaseApplication

		application = self.application
		options = dict(self.options)
		when_ready = options.pop('when_ready', None)
		post_worker_init = options.pop('post_worker_init', None)
		worker_exit = options.pop('worker_exit', None)
		pre_request = options.pop('pre_request', None)
		address = f'[{self.host}]' if ':' in self.host else self.host
		options.update(
			bind=f'{address}:{self.port}',
			workers=self.workers,
			worker_class=self.worker_class,
		)

		def ready(server: Any) -> None:
			if when_ready is not None:
				when_ready(server)
			startup(
				application,
				'Gunicorn',
				self.host,
				self.port,
			)
			return

		def start(worker: Any) -> None:
			application.start()
			if post_worker_init is not None:
				post_worker_init(worker)
			return

		def prepare(
			worker: Any,
			request: Any,
		) -> None:
			if pre_request is not None:
				pre_request(
					worker,
					request,
				)
			request.body = Body(request)
			if any(
				key == 'UPGRADE' and value.lower() == 'websocket'
				for key, value in request.headers
			):
				request.force_close()
			return

		def stop(
			server: Any,
			worker: Any,
		) -> None:
			try:
				application.stop()
			finally:
				if worker_exit is not None:
					worker_exit(
						server,
						worker,
					)
			return

		options.update(
			when_ready=ready,
			post_worker_init=start,
			worker_exit=stop,
			pre_request=prepare,
		)

		class GunicornApplication(BaseApplication):
			def load_config(self) -> None:
				for key, value in options.items():
					self.cfg.set(
						key,
						value,
					)
				return

			def load(self) -> RequestApplication:
				return RequestApplication(application)

		GunicornApplication().run()
		return
