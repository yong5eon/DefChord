from http import HTTPStatus


class Error(Exception):
	"""Represent an error to be returned as an HTTP response."""

	def __init__(
		self,
		status: int,
		reason: str,
	):
		super().__init__(reason)
		self.status = status
		self.message = HTTPStatus(status).phrase
		self.reason = reason
		return


class ClientError(Error):
	"""Represent an invalid client request."""

	def __init__(
		self,
		reason: str,
		status: int = 400,
	):
		if not 400 <= status < 500:
			raise ValueError('ClientError status code must be in the 4xx range')
		super().__init__(
			status,
			reason,
		)
		return
