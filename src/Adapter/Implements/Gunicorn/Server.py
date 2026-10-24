from os import name
from logging import getLogger
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
	"""Start and stop the application in each Gunicorn worker."""

	logger = getLogger('DefEssential.Server')

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
		# Gunicorn is an optional dependency and cannot be imported on Windows.
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
			for listener in server.LISTENERS:
				self.logger.info(
					'Server ready: adapter=Gunicorn address=%s',
					listener.getsockname(),
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

		self.logger.info('Server starting: adapter=Gunicorn host=%s port=%s', self.host, self.port)
		try:
			GunicornApplication().run()
		except SystemExit as error:
			if error.code:
				self.logger.error('Server exited unsuccessfully: adapter=Gunicorn code=%s', error.code)
			raise
		except Exception:
			self.logger.exception('Server execution failed: adapter=Gunicorn')
			raise
		self.logger.info('Server stopped: adapter=Gunicorn')
		return
