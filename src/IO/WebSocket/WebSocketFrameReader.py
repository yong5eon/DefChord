from struct import unpack

from ...Error import ClientError
from ..RequestReader import (
	ClientDisconnected,
	RequestReader,
)
from .WebSocketError import WebSocketError
from .WebSocketFrame import WebSocketFrame

__all__ = (
	'WebSocketFrameReader',
)


class WebSocketFrameReader:
	"""Read client frames one at a time from an upgraded connection and validate frame rules."""

	def __init__(
		self,
		reader: RequestReader,
		limit: int,
	):
		self.reader = reader
		self.limit = limit
		return

	def exact(
		self,
		size: int,
	) -> bytes:
		try:
			return self.reader.exact(size)
		except ClientError as error:
			# RequestReader.exact() treats EOF as a body error, but EOF after an upgrade means disconnection.
			raise ClientDisconnected(error.reason) from error

	def unmask(
		self,
		data: bytes,
		mask: bytes,
	) -> bytes:
		size = len(data)
		key = (mask * (size // 4 + 1))[:size]
		return (int.from_bytes(data, 'big') ^ int.from_bytes(key, 'big')).to_bytes(
			size,
			'big',
		)

	def read(self) -> WebSocketFrame:
		first, second = self.exact(2)
		if first & 0x70:
			raise WebSocketError(
				1002,
				'Reserved bits must be zero',
			)
		final = bool(first & 0x80)
		opcode = first & 0x0F
		if opcode not in WebSocketFrame.OPCODES:
			raise WebSocketError(
				1002,
				'Unknown opcode',
			)
		if not second & 0x80:
			raise WebSocketError(
				1002,
				'Client frames must be masked',
			)
		size = second & 0x7F
		if size == 126:
			size = unpack('!H', self.exact(2))[0]
		elif size == 127:
			size = unpack('!Q', self.exact(8))[0]
			if size >> 63:
				raise WebSocketError(
					1002,
					'Invalid payload length',
				)
		control = opcode >= WebSocketFrame.CLOSE
		if control and (not final or size > 125):
			raise WebSocketError(
				1002,
				'Control frames must be final and at most 125 bytes',
			)
		if not control and size > self.limit:
			raise WebSocketError(
				1009,
				'Message too big',
			)
		mask = self.exact(4)
		return WebSocketFrame(
			opcode,
			self.unmask(
				self.exact(size),
				mask,
			),
			final,
		)
