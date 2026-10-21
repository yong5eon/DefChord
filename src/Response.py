from email.message import Message
from http import HTTPStatus
from typing import (
	Iterable,
	Mapping,
	Optional,
	Union,
)


class Response:
	"""바이트열 또는 순차 출력으로 구성하는 HTTP 응답."""

	def __init__(
		self,
		status: int = 200,
		message: Optional[str] = None,
		headers: Optional[Mapping[str, str]] = None,
		body: Union[bytes, Iterable[bytes]] = b'',
		format: Optional[str] = None,
		charset: Optional[str] = None,
	):
		self.status = status
		self.message = HTTPStatus(status).phrase if message is None else message
		self.props = Message()
		for key, value in headers.items() if headers is not None else ():
			self.header(
				key,
				value,
			)
		if format is not None:
			self.header(
				'Content-Type',
				format + ('; charset=' + charset if charset is not None else ''),
			)
		self.body = body
		return

	def header(
		self,
		key: str,
		value: Optional[str] = None,
	) -> Optional[str]:
		if value is None:
			return self.props.get(key)
		if '\r' in key or '\n' in key or '\r' in value or '\n' in value:
			raise ValueError('응답 헤더에 줄바꿈을 포함할 수 없습니다')
		del self.props[key]
		self.props[key] = value
		return None

	def headers(self) -> list:
		return list(self.props.items())

	def close(self) -> None:
		close = getattr(self.body, 'close', None)
		if close is not None:
			close()
		return
