import asyncio
from asyncio import Queue
from queue import Queue as SyncQueue
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
		self.chunked = False
		return

	def write(self, data: bytes) -> int:
		length = len(data)
		if self.chunked:
			line, data = data.split(b'\r\n', 1)
			size = int(line.split(b';', 1)[0], 16)
			if size == 0:
				return length
			data = data[:size]
		if data:
			self.loop.call_soon_threadsafe(self.events.put_nowait, ('body', data))
		return length

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
		await asyncio.to_thread(self.start)
		headers = {
			key.decode('latin-1'): value.decode('latin-1')
			for key, value in scope.get('headers', ())
		}
		length = headers.get('content-length')
		first_message = None
		first_body = b''
		prefetched = False
		if length is None and headers.get('transfer-encoding', '').lower() != 'chunked':
			prefetched = True
			while True:
				first_message = await receive()
				if first_message['type'] == 'http.disconnect':
					first_message = None
					break
				first_body = first_message.get('body', b'')
				if first_body or not first_message.get('more_body', False):
					break
		chunked = length is None and (
			headers.get('transfer-encoding', '').lower() == 'chunked'
			or bool(first_body)
		)
		if chunked:
			headers['Transfer-Encoding'] = 'chunked'
		input_events = SyncQueue()
		input_reader = _Input(input_events)
		output_events = Queue()
		output = _Output(asyncio.get_running_loop(), output_events)

		def enqueue_body(message) -> bool:
			if message is None or message['type'] == 'http.disconnect':
				return True
			body = message.get('body', b'')
			if body:
				input_events.put(
					format(len(body), 'x').encode('ascii') + b'\r\n' + body + b'\r\n'
					if chunked else body,
				)
			return not message.get('more_body', False)

		async def receive_body() -> None:
			try:
				if prefetched and enqueue_body(first_message):
					return
				while True:
					message = await receive()
					if enqueue_body(message):
						break
			finally:
				if chunked:
					input_events.put(b'0\r\n\r\n')
				input_events.put(None)

		def sender(response: Response, chunked: bool) -> None:
			output.status = response.status
			output.chunked = chunked
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
			size=None if chunked else int(length) if length else 0,
			chunked=chunked,
		)
		writer = ResponseWriter(
			sender,
			output,
			method=scope.get('method', 'GET'),
			version='HTTP/' + scope.get('http_version', '1.1'),
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

		async def run() -> None:
			try:
				await asyncio.to_thread(self.dispatch, request)
			finally:
				await output_events.put(('end',))
			return

		app_task = asyncio.create_task(run())
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
