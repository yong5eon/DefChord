from email.message import Message
from io import BytesIO
from re import fullmatch
from typing import (
	Any,
	Mapping,
	Optional,
)
from urllib.parse import (
	parse_qs,
	urlsplit,
)
from uuid import uuid4

from .RequestReader import RequestReader
from .ResponseWriter import ResponseWriter
from .Error import ClientError


class Request:
	"""서버 환경 딕셔너리와 독립적인 HTTP 요청."""

	def __init__(
		self,
		address: str,
		port: int,
		method: str,
		uri: str,
		parameters: Optional[Mapping[str, str]] = None,
		headers: Optional[Mapping[str, str]] = None,
		reader: Optional[RequestReader] = None,
		writer: Optional[ResponseWriter] = None,
	):
		self.id = uuid4().hex
		self.address = address
		self.port = port
		self.method = method
		self.uri = uri
		parsed = urlsplit(uri)
		self.path = parsed.path
		self.querystring = parsed.query
		self.params = dict(parameters) if parameters is not None else {}
		self.args = {
			key: values[0] if len(values) == 1 else values
			for key, values in parse_qs(
				parsed.query,
				keep_blank_values=True,
			).items()
		}
		self.props = Message()
		for key, value in headers.items() if headers is not None else ():
			self.props[key] = value
		self.reader = reader if reader is not None else RequestReader(BytesIO())
		self.response_writer = writer
		self.body: Any = None
		self.session: Any = None
		return

	@property
	def writer(self) -> ResponseWriter:
		"""실행 계층이 제공한 응답 Writer를 반환한다."""
		if self.response_writer is None:
			raise RuntimeError('이 요청에는 응답 Writer가 연결되지 않았습니다')
		return self.response_writer

	def header(
		self,
		key: str,
		value: Optional[str] = None,
	) -> Optional[str]:
		if value is not None:
			del self.props[key]
			self.props[key] = value
			return None
		return self.props.get(key)

	def headers(self) -> list:
		return list(self.props.items())

	@property
	def parameters(self) -> dict:
		return self.params

	@property
	def qs(self) -> dict:
		return self.args

	@property
	def size(self) -> Optional[int]:
		value = self.header('Content-Length')
		return int(value) if value is not None else None

	@property
	def format(self) -> Optional[str]:
		value = self.header('Content-Type')
		if value is None:
			return None
		format = value.split(';', 1)[0].strip().lower()
		token = r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
		if fullmatch(token + '/' + token, format) is None:
			raise ClientError('잘못된 Content-Type')
		return format

	@property
	def charset(self) -> Optional[str]:
		return self.props.get_content_charset()
