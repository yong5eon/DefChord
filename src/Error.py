from http import HTTPStatus
from typing import (
	Mapping,
	Optional,
)


class Error(Exception):
	"""Represent an error to be returned as an HTTP response."""

	def __init__(
		self,
		status: int,
		reason: str,
		headers: Optional[Mapping[str, str]] = None,
	):
		super().__init__(reason)
		self.status = status
		self.message = HTTPStatus(status).phrase
		self.reason = reason
		self.headers = dict(headers) if headers is not None else {}
		return


class ClientError(Error):
	"""Represent an invalid client request."""

	def __init__(
		self,
		reason: str,
		status: int = 400,
		headers: Optional[Mapping[str, str]] = None,
	):
		if not 400 <= status < 500:
			raise ValueError('ClientError status code must be in the 4xx range')
		super().__init__(
			status,
			reason,
			headers,
		)
		return


class ServerError(Error):
	"""Represent a server-side processing failure."""

	def __init__(
		self,
		reason: str,
		status: int = 500,
		headers: Optional[Mapping[str, str]] = None,
	):
		if not 500 <= status < 600:
			raise ValueError('ServerError status code must be in the 5xx range')
		super().__init__(
			status,
			reason,
			headers,
		)
		return
