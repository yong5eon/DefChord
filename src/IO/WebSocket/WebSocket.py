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
	"""업그레이드된 HTTP 연결에서 WebSocket 메시지를 주고받는다.

	receive()는 한 스레드에서만 호출한다. send(), ping(), close()는 다른 스레드에서도 호출할 수 있다.
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
		"""핸드셰이크를 검사하고 101 응답을 보낸다. 실패하면 101 전이므로 일반 오류 응답이 나간다."""
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
		"""str은 text 메시지로, bytes는 binary 메시지로 보낸다."""
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
		"""다음 메시지를 반환한다. 연결이 닫히는 과정에 들어가면 None을 반환한다.

		ping에는 자동으로 pong을 보낸다. 프로토콜 위반은 닫기 코드를 보낸 뒤 None을 반환하고,
		TCP 연결이 끊기면 ClientDisconnected가 전파된다.
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
		"""닫기 프레임을 보내고 클라이언트의 닫기 프레임을 받을 때까지 남은 메시지를 버린다."""
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
