from typing import Any

from ....Application import Application
from ....Startup import startup
from ...Server import Server as ServerAdapter

__all__ = (
	'Server',
)


class Server(ServerAdapter):
	"""a2wsgi로 동기 애플리케이션을 Uvicorn에서 실행한다."""

	def __init__(
		self,
		host: str,
		port: int,
		application: Application,
		*,
		wsgi_workers: int = 10,
		send_queue_size: int = 10,
		**options: Any,
	):
		super().__init__(
			host,
			port,
			application,
		)
		if wsgi_workers < 1 or send_queue_size < 1:
			raise ValueError('wsgi_workers and send_queue_size must be at least 1')
		if options.get('workers') not in (
			None,
			1,
		) or options.get('reload', False):
			raise ValueError('Application instances require workers=1 and reload=False')
		if options.get('interface', 'asgi3') != 'asgi3':
			raise ValueError('a2wsgi requires interface=asgi3')
		if any(key == 'ws' or key.startswith('ws_') for key in options):
			raise ValueError('The adapter manages WebSocket framing; configure limits and ping in WebSocket handlers')
		self.wsgi_workers = wsgi_workers
		self.send_queue_size = send_queue_size
		self.options = options
		return

	def run(self) -> None:
		# 기본 서버를 사용할 때 선택적 의존성을 가져오지 않는다.
		from .HTTP import Middleware
		from .WebSocket import WebSocketProtocol
		from uvicorn import (
			Config,
			Server as UvicornServer,
		)

		middleware = Middleware(
			self.application,
			workers=self.wsgi_workers,
			queue_size=self.send_queue_size,
		)
		try:
			application = self.application

			class NativeWebSocketProtocol(WebSocketProtocol):
				def __init__(
					self,
					config,
					server_state,
					app_state,
				):
					super().__init__(
						config,
						server_state,
						app_state,
						application,
						middleware.executor,
					)
					return

			options = dict(self.options)
			options['workers'] = 1
			options['interface'] = 'asgi3'
			server = UvicornServer(Config(
				middleware,
				host=self.host,
				port=self.port,
				ws=NativeWebSocketProtocol,
				**options,
			))
			self.application.start()
			try:
				startup(
					self.application,
					'Uvicorn',
					self.host,
					self.port,
				)
				server.run()
			finally:
				self.application.stop()
		finally:
			middleware.executor.shutdown(wait=True)
		return
