from json import loads
from typing import (
	Any,
	Callable,
	Optional,
	Union,
)
from urllib.parse import parse_qs

from ..Error import (
	ClientError,
	Error,
)
from ..Request import Request
from ..RequestReader import RequestReader
from ..Validator import (
	Pattern,
	Validator,
)
from .ContentReader import ContentReader


class ByteStringContentReader(ContentReader):
	"""명시적인 바이너리 본문을 읽고 검증한다."""

	def __init__(
		self,
		va: Union[Validator, Pattern, None] = None,
		error: Optional[Error] = None,
		typeerror: Optional[Error] = None,
	):
		self.va = Validator(va) if isinstance(va, Pattern) else va
		self.error = error
		self.typeerror = typeerror
		return

	def validate(
		self,
		content: Any,
	) -> Any:
		return self.va(content) if self.va is not None else content

	def require(
		self,
		request: Request,
		format: str,
	) -> None:
		if request.format != format:
			raise self.typeerror if self.typeerror is not None else ClientError(
				'지원하지 않는 본문 형식',
				status=415,
			)
		return

	def __call__(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		try:
			return self.read_content(
				request,
				reader,
			)
		except Error as error:
			if self.error is not None and error is not self.typeerror:
				raise self.error from error
			raise
		except (ValueError, TypeError, LookupError) as error:
			raise self.error if self.error is not None else ClientError(str(error)) from error

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		self.require(
			request,
			'application/octet-stream',
		)
		return self.validate(reader.read())


class StreamContentReader(ByteStringContentReader):
	"""길이 지정·Chunked 입력을 미리 읽지 않고 바이너리 스트림으로 전달한다."""

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> RequestReader:
		self.require(
			request,
			'application/octet-stream',
		)
		return reader


class TextContentReader(ByteStringContentReader):
	"""text/* 본문을 문자열로 변환한다."""

	def decode(
		self,
		request: Request,
		reader: RequestReader,
	) -> str:
		try:
			return reader.read().decode(request.charset or 'utf-8')
		except (UnicodeError, LookupError) as error:
			raise ClientError('잘못된 본문 문자 인코딩') from error

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		if request.format is None or not request.format.startswith('text/'):
			raise self.typeerror if self.typeerror is not None else ClientError(
				'지원하지 않는 텍스트 본문 형식',
				status=415,
			)
		return self.validate(self.decode(
			request,
			reader,
		))


class FormUrlEncodedContentReader(TextContentReader):
	"""URL 인코딩된 폼을 단일 값 또는 복수 값으로 읽는다."""

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		self.require(
			request,
			'application/x-www-form-urlencoded',
		)
		values = parse_qs(
			self.decode(
				request,
				reader,
			),
			keep_blank_values=True,
		)
		return self.validate({
			key: items[0] if len(items) == 1 else items
			for key, items in values.items()
		})


class JavaScriptObjectNotationContentReader(TextContentReader):
	"""JSON 본문을 읽고 선택적인 값 변환과 검증을 수행한다."""

	def __init__(
		self,
		va: Union[Validator, Pattern, None] = None,
		typereader: Optional[Callable[[Any], Any]] = None,
		error: Optional[Error] = None,
		typeerror: Optional[Error] = None,
	):
		super().__init__(
			va=va,
			error=error,
			typeerror=typeerror,
		)
		self.typereader = typereader
		return

	def convert(
		self,
		value: Any,
	) -> Any:
		if isinstance(value, dict):
			return {
				key: self.convert(item) for key, item in value.items()
			}
		if isinstance(value, list):
			return [self.convert(item) for item in value]
		return self.typereader(value) if self.typereader is not None else value

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		self.require(
			request,
			'application/json',
		)
		try:
			value = loads(self.decode(
				request,
				reader,
			))
		except ValueError as error:
			raise ClientError('잘못된 JSON 본문') from error
		if self.typereader is not None:
			value = self.convert(value)
		return self.validate(value)
