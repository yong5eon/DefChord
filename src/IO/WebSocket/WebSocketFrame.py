from struct import pack

__all__ = (
	'WebSocketFrame',
)


class WebSocketFrame:
	"""WebSocket 프레임 하나를 표현하고 서버가 보내는 마스크 없는 바이트로 인코딩한다."""

	CONTINUATION = 0x0
	TEXT = 0x1
	BINARY = 0x2
	CLOSE = 0x8
	PING = 0x9
	PONG = 0xA
	OPCODES = (
		CONTINUATION,
		TEXT,
		BINARY,
		CLOSE,
		PING,
		PONG,
	)

	def __init__(
		self,
		opcode: int,
		payload: bytes = b'',
		final: bool = True,
	):
		if opcode not in self.OPCODES:
			raise ValueError('Unknown WebSocket opcode')
		if opcode >= self.CLOSE and (not final or len(payload) > 125):
			raise ValueError('Control frames must be final and at most 125 bytes')
		self.opcode = opcode
		self.payload = payload
		self.final = final
		return

	@property
	def control(self) -> bool:
		return self.opcode >= self.CLOSE

	def encode(self) -> bytes:
		first = (0x80 if self.final else 0) | self.opcode
		size = len(self.payload)
		if size < 126:
			header = pack(
				'!BB',
				first,
				size,
			)
		elif size < 65536:
			header = pack(
				'!BBH',
				first,
				126,
				size,
			)
		else:
			header = pack(
				'!BBQ',
				first,
				127,
				size,
			)
		return header + self.payload
