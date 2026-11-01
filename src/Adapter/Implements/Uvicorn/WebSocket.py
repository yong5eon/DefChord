from asyncio import (
	CancelledError,
	Event,
	Protocol,
	StreamReader,
	Transport,
	get_running_loop,
	shield,
)
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from logging import getLogger
from socket import socket
from socketserver import BaseServer
from typing import (
	Any,
	cast,
)

from ....Application import Application
from ....IO.RequestReader import ClientDisconnected
from ....IO.WebSocket.WebSocketFrame import WebSocketFrame
from ..Python.Server import ServerRequestHandler
from .Portal import Portal

__all__ = (
	'ServerContext',
	'Connection',
	'WebSocketProtocol',
)


class ServerContext(BaseServer):
	app: Application


class Connection:
	"""Expose an asyncio connection as a socket to the existing HTTP/WebSocket handler."""

	def __init__(
		self,
		protocol: 'WebSocketProtocol',
	):
		self.protocol = protocol
		return

	def makefile(
		self,
		mode: str,
		buffering: int = -1,
	) -> 'Connection':
		if mode != 'rb' or buffering not in (
			-1,
			0,
		):
			raise ValueError('Only a binary input file is supported')
		return self

	def read(
		self,
		size: int = -1,
		/,
	) -> bytes:
		return self.protocol.portal.call(self.protocol.reader.read(size))

	def readline(
		self,
		size: int = -1,
		/,
	) -> bytes:
		return self.protocol.portal.call(self.protocol.readline(size))

	def sendall(
		self,
		data: bytes,
	) -> None:
		self.protocol.portal.call(self.protocol.write(data))
		return

	def close(self) -> None:
		return


class WebSocketProtocol(Protocol):
	"""Run the existing RFC 6455 handler on Uvicorn's upgraded connection."""

	logger = getLogger('DefChord.Server')

	def __init__(
		self,
		config: Any,
		server_state: Any,
		app_state: dict[str, Any],
		application: Application,
		executor: ThreadPoolExecutor,
	):
		self.application = application
		self.executor = executor
		self.state = server_state
		self.portal = Portal(get_running_loop())
		self.reader = StreamReader(limit=65536)
		self.writable = Event()
		self.writable.set()
		self.transport: Transport
		self.task = None
		self.upgraded = False
		return

	def connection_made(
		self,
		transport,
	) -> None:
		if not isinstance(transport, Transport):
			raise TypeError('A stream transport is required')
		self.transport = transport
		self.reader.set_transport(transport)
		self.state.connections.add(self)
		self.task = self.portal.loop.create_task(self.run())
		self.state.tasks.add(self.task)
		self.task.add_done_callback(self.state.tasks.discard)
		return

	def data_received(
		self,
		data: bytes,
	) -> None:
		self.reader.feed_data(data)
		return

	def eof_received(self) -> None:
		self.reader.feed_eof()
		return

	def connection_lost(
		self,
		error,
	) -> None:
		self.state.connections.discard(self)
		if error is None:
			self.reader.feed_eof()
		else:
			self.reader.set_exception(error)
		self.writable.set()
		return

	async def readline(
		self,
		size: int,
	) -> bytes:
		data = bytearray()
		while size < 0 or len(data) < size:
			part = await self.reader.read(1)
			if not part:
				break
			data.extend(part)
			if part == b'\n':
				break
		return bytes(data)

	def pause_writing(self) -> None:
		self.writable.clear()
		return

	def resume_writing(self) -> None:
		self.writable.set()
		return

	async def write(
		self,
		data: bytes,
	) -> None:
		await self.writable.wait()
		if self.transport.is_closing():
			raise ClientDisconnected('WebSocket connection is closed')
		self.transport.write(data)
		if data.startswith(b'HTTP/1.1 101 '):
			self.upgraded = True
		return

	def shutdown(self) -> None:
		if self.upgraded and not self.transport.is_closing():
			self.transport.write(WebSocketFrame(
				WebSocketFrame.CLOSE,
				b'\x03\xe9',
			).encode())
		self.transport.close()
		self.reader.feed_eof()
		return

	async def run(self) -> None:
		def handle() -> None:
			server = ServerContext(
				self.transport.get_extra_info('sockname'),
				ServerRequestHandler,
			)
			# The standard handler requires the nominal socket type but uses only the file and send contracts below.
			connection = Connection(self)
			server.app = self.application
			ServerRequestHandler(
				cast(socket, connection),
				self.transport.get_extra_info('peername'),
				server,
			)
			return

		worker = self.portal.loop.run_in_executor(
			self.executor,
			handle,
		)
		try:
			await shield(worker)
		except CancelledError:
			self.portal.close()
			with suppress(ClientDisconnected):
				await worker
			raise
		except Exception:
			self.logger.exception('WebSocket connection handling failed: adapter=Uvicorn')
		finally:
			self.portal.close()
			self.transport.close()
		return
