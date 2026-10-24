from logging import getLogger
from struct import (
	pack,
	unpack,
)
from threading import Lock
from typing import (
	Optional,
	Union,
)

from ...Request import Request
from .WebSocketError import WebSocketError
from .WebSocketFrame import WebSocketFrame
from .WebSocketFrameReader import WebSocketFrameReader
from .WebSocketHandshake import WebSocketHandshake

__all__ = (
	'WebSocket',
)


class WebSocket:
	"""Exchange WebSocket messages over an upgraded HTTP connection.

	Call receive() from a single thread. send(), ping(), and close() may also be
	called from other threads.
	"""

	logger = getLogger('DefEssential.IO.WebSocket')

	def __init__(
		self,
		request: Request,
		limit: int,
	):
		if limit <= 0:
			raise ValueError('Message size limit must be positive')
		self.request = request
		self.limit = limit
		self.handshake = WebSocketHandshake(request)
		self.frames = WebSocketFrameReader(
			request.reader,
			limit,
		)
		self.lock = Lock()
		self.accepted = False
		self.close_sent = False
		self.closed = False
		self.code: Optional[int] = None
		self.reason = ''
		return

	@property
	def protocols(self) -> list[str]:
		return self.handshake.protocols

	def accept(
		self,
		protocol: Optional[str] = None,
	) -> None:
		"""Validate the handshake and send a 101 response. On failure, a regular error response is sent because the connection has not been upgraded."""
		if self.accepted:
			raise RuntimeError('WebSocket has already been accepted')
		self.request.writer.upgrade(self.handshake.response(protocol))
		self.accepted = True
		self.logger.debug('WebSocket upgraded: request_id=%s status=101', self.request.id)
		return

	def valid_code(
		self,
		code: int,
	) -> bool:
		return code in (
			1000,
			1001,
			1002,
			1003,
			1007,
			1008,
			1009,
			1010,
			1011,
			1012,
			1013,
			1014,
		) or 3000 <= code <= 4999

	def write(
		self,
		frame: WebSocketFrame,
	) -> None:
		with self.lock:
			if not self.accepted:
				raise RuntimeError('WebSocket must be accepted first')
			if self.close_sent:
				raise RuntimeError('Cannot send after the WebSocket close frame')
			if frame.opcode == WebSocketFrame.CLOSE:
				self.close_sent = True
			self.request.writer.write(frame.encode())
			self.request.writer.flush()
		return

	def send(
		self,
		message: Union[str, bytes],
	) -> None:
		"""Send str values as text messages and bytes values as binary messages."""
		if isinstance(message, str):
			frame = WebSocketFrame(
				WebSocketFrame.TEXT,
				message.encode('utf-8'),
			)
		elif isinstance(message, bytes):
			frame = WebSocketFrame(
				WebSocketFrame.BINARY,
				message,
			)
		else:
			raise TypeError('WebSocket messages must be str or bytes')
		self.write(frame)
		return

	def ping(
		self,
		data: bytes = b'',
	) -> None:
		self.write(WebSocketFrame(
			WebSocketFrame.PING,
			data,
		))
		return

	def close_frame(
		self,
		code: int,
		reason: str,
	) -> WebSocketFrame:
		return WebSocketFrame(
			WebSocketFrame.CLOSE,
			pack('!H', code) + reason.encode('utf-8'),
		)

	def receive_close(
		self,
		frame: WebSocketFrame,
	) -> None:
		payload = frame.payload
		if len(payload) == 1:
			raise WebSocketError(
				1002,
				'Invalid close frame',
			)
		code = unpack('!H', payload[:2])[0] if payload else None
		if code is not None and not self.valid_code(code):
			raise WebSocketError(
				1002,
				'Invalid close code',
			)
		try:
			reason = payload[2:].decode('utf-8')
		except UnicodeDecodeError as error:
			raise WebSocketError(
				1007,
				'Invalid close reason',
			) from error
		self.code = code
		self.reason = reason
		self.closed = True
		with self.lock:
			echo = not self.close_sent
		if echo:
			self.write(WebSocketFrame(
				WebSocketFrame.CLOSE,
				payload[:2],
			))
		self.logger.debug('WebSocket closed: request_id=%s code=%s', self.request.id, self.code)
		return

	def fail(
		self,
		error: WebSocketError,
	) -> None:
		self.logger.warning(
			'WebSocket protocol error: request_id=%s code=%s',
			self.request.id,
			error.code,
		)
		self.code = error.code
		self.reason = error.reason
		self.closed = True
		with self.lock:
			send = not self.close_sent
		if send:
			self.write(self.close_frame(
				error.code,
				error.reason,
			))
		self.logger.debug('WebSocket failed: request_id=%s code=%s', self.request.id, error.code)
		return

	def receive(self) -> Union[str, bytes, None]:
		"""Return the next message, or None once the connection starts closing.

		Automatically reply to ping frames with pong. On a protocol violation,
		send a close code and return None. Propagate ClientDisconnected if the
		TCP connection is lost.
		"""
		if not self.accepted:
			raise RuntimeError('WebSocket must be accepted first')
		if self.closed:
			return None
		opcode: Optional[int] = None
		parts = []
		size = 0
		try:
			while True:
				frame = self.frames.read()
				if frame.opcode == WebSocketFrame.CLOSE:
					self.receive_close(frame)
					return None
				if frame.opcode == WebSocketFrame.PING:
					with self.lock:
						reply = not self.close_sent
					if reply:
						self.write(WebSocketFrame(
							WebSocketFrame.PONG,
							frame.payload,
						))
					continue
				if frame.opcode == WebSocketFrame.PONG:
					continue
				if frame.opcode == WebSocketFrame.CONTINUATION:
					if opcode is None:
						raise WebSocketError(
							1002,
							'Unexpected continuation frame',
						)
				elif opcode is not None:
					raise WebSocketError(
						1002,
						'Expected a continuation frame',
					)
				else:
					opcode = frame.opcode
				size += len(frame.payload)
				if size > self.limit:
					raise WebSocketError(
						1009,
						'Message too big',
					)
				parts.append(frame.payload)
				if frame.final:
					break
			data = b''.join(parts)
			if opcode == WebSocketFrame.BINARY:
				return data
			try:
				return data.decode('utf-8')
			except UnicodeDecodeError as error:
				raise WebSocketError(
					1007,
					'Invalid UTF-8 text',
				) from error
		except WebSocketError as error:
			self.fail(error)
			return None

	def close(
		self,
		code: int = 1000,
		reason: str = '',
	) -> None:
		"""Send a close frame and discard messages until the client's close frame arrives."""
		if not self.valid_code(code):
			raise ValueError('Invalid WebSocket close code')
		if len(reason.encode('utf-8')) > 123:
			raise ValueError('WebSocket close reason must be at most 123 bytes')
		with self.lock:
			send = not self.close_sent
		if send:
			self.write(self.close_frame(
				code,
				reason,
			))
		while not self.closed:
			self.receive()
		return
