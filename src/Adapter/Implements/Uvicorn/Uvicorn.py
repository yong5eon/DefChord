import asyncio
from asyncio import Queue
from threading import Lock
from typing import Optional

from ...Adapter import Adapter
from ....Request import Request
from ....RequestReader import RequestReader
from ....Response import Response
from ....ResponseWriter import ResponseWriter


class _Output:
	def __init__(self, loop, events):
		self.loop = loop
		self.events = events
		self.status: Optional[int] = None
		return

	def write(self, data: bytes) -> int:
		self.loop.call_soon_threadsafe(self.events.put_nowait, ('body', data))
		return len(data)

	def flush(self) -> None:
		return


class _Input:
	def __init__(self, events):
		self.events = events
		self.buffer = bytearray()
		self.done = False
		return

	def read(self, size: int = -1) -> bytes:
		while not self.done and (size < 0 or len(self.buffer) < size):
			item = self.events.get()
			if item is None:
				self.done = True
			else:
				self.buffer.extend(item)
		count = len(self.buffer) if size < 0 else min(size, len(self.buffer))
		data = bytes(self.buffer[:count])
		del self.buffer[:count]
		return data

	def readline(self, size: int = -1) -> bytes:
		while not self.done and b'\n' not in self.buffer and (size < 0 or len(self.buffer) < size):
			item = self.events.get()
			if item is None:
				self.done = True
			else:
				self.buffer.extend(item)
		end = self.buffer.find(b'\n') + 1
		if end == 0:
			end = len(self.buffer)
		if size >= 0:
			end = min(end, size)
		data = bytes(self.buffer[:end])
		del self.buffer[:end]
		return data


class UvicornAdapter(Adapter):
	"""Expose a DefEssential Application as an ASGI callable for Uvicorn."""

	def __init__(self, app):
		super().__init__(app)
		self._lifecycle_lock = Lock()
		return

	def start(self) -> None:
		with self._lifecycle_lock:
			if not self.app.running:
				self.app.start()
		return

	def stop(self) -> None:
		with self._lifecycle_lock:
			if self.app.running:
				self.app.stop()
		return

	async def __call__(
		self,
		scope,
		receive,
		send,
	):
		if scope['type'] == 'lifespan':
			await self.lifespan(receive, send)
		elif scope['type'] == 'http':
			await self.http(scope, receive, send)
		else:
			raise ValueError('UvicornAdapter supports ASGI HTTP and lifespan scopes')
		return

	async def lifespan(self, receive, send) -> None:
		while True:
			message = await receive()
			if message['type'] == 'lifespan.startup':
				try:
					self.start()
				except Exception as error:
					await send({
						'type': 'lifespan.startup.failed',
						'message': str(error),
					})
					return
				await send({'type': 'lifespan.startup.complete'})
			elif message['type'] == 'lifespan.shutdown':
				try:
					self.stop()
				except Exception as error:
					await send({
						'type': 'lifespan.shutdown.failed',
						'message': str(error),
					})
				else:
					await send({'type': 'lifespan.shutdown.complete'})
				return

	async def http(self, scope, receive, send) -> None:
		headers = {
			key.decode('latin-1'): value.decode('latin-1')
			for key, value in scope.get('headers', ())
		}
		length = headers.get('content-length')
		input_events = __import__('queue').Queue()
		input_reader = _Input(input_events)
		output_events = Queue()
		output = _Output(asyncio.get_running_loop(), output_events)

		async def receive_body() -> None:
			try:
				while True:
					message = await receive()
					if message['type'] == 'http.disconnect':
						break
					body = message.get('body', b'')
					if body:
						input_events.put(body)
					if not message.get('more_body', False):
						break
			finally:
				input_events.put(None)

		def sender(response: Response, chunked: bool) -> None:
			output.status = response.status
			headers_out = [
				(key.lower().encode('latin-1'), value.encode('latin-1'))
				for key, value in response.headers()
				if key.lower() not in ('transfer-encoding', 'connection')
			]
			output.loop.call_soon_threadsafe(
				output_events.put_nowait,
				('start', response.status, headers_out),
			)
			return

		reader = RequestReader(
			input_reader,
			size=int(length) if length else 0,
		)
		writer = ResponseWriter(
			sender,
			output,
			method=scope.get('method', 'GET'),
			version=scope.get('http_version', '1.1'),
		)
		client = scope.get('client') or ('', 0)
		request = Request(
			address=client[0],
			port=client[1],
			method=scope.get('method', 'GET'),
			uri=scope.get('path', '/') + (
				'?' + scope['query_string'].decode('latin-1')
				if scope.get('query_string') else ''
			),
			headers=headers,
			reader=reader,
			writer=writer,
		)
		input_task = asyncio.create_task(receive_body())
		app_task = asyncio.create_task(asyncio.to_thread(self.dispatch, request))
		started = False
		try:
			while True:
				event = await output_events.get()
				if event[0] == 'start':
					_, status, response_headers = event
					await send({
						'type': 'http.response.start',
						'status': status,
						'headers': response_headers,
					})
					started = True
				elif event[0] == 'body':
					if started:
						await send({
							'type': 'http.response.body',
							'body': event[1],
							'more_body': True,
						})
				else:
					if started:
						await send({
							'type': 'http.response.body',
							'body': b'',
							'more_body': False,
						})
					break
			await app_task
		finally:
			if not input_task.done():
				input_task.cancel()
			await asyncio.gather(input_task, return_exceptions=True)
		return
