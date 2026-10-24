__all__ = (
	'WebSocketError',
)


class WebSocketError(Exception):
	"""Represent a client WebSocket protocol violation with a close code."""

	def __init__(
		self,
		code: int,
		reason: str,
	):
		super().__init__(reason)
		self.code = code
		self.reason = reason
		return
