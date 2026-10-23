__all__ = (
	'WebSocketError',
)


class WebSocketError(Exception):
	"""클라이언트의 WebSocket 프로토콜 위반을 닫기 코드와 함께 표현한다."""

	def __init__(
		self,
		code: int,
		reason: str,
	):
		super().__init__(reason)
		self.code = code
		self.reason = reason
		return
