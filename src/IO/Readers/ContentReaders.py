from json import loads
from typing import (
	Any,
	Callable,
	Optional,
	Union,
)
from urllib.parse import parse_qs

from ...Error import (
	ClientError,
	Error,
)
from ...Request import Request
from ..RequestReader import RequestReader
from ...Validator import (
	Pattern,
	Validator,
)
from .ChunkedStream import ChunkedStream
from .ContentReader import ContentReader


class ByteStringContentReader(ContentReader):
	"""Read and validate a binary body regardless of its Content-Type."""

	def __init__(
		self,
		va: Union[Validator, Pattern, None] = None,
		error: Optional[Error] = None,
	):
		self.va = Validator(va) if isinstance(va, Pattern) else va
		self.error = error
		return

	def validate(
		self,
		content: Any,
	) -> Any:
		return self.va(content) if self.va is not None else content

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
			if self.error is not None:
				raise self.error from error
			raise
		except (ValueError, TypeError, LookupError) as error:
			raise self.error if self.error is not None else ClientError(str(error)) from error

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		return self.validate(reader.read())


class StreamContentReader(ByteStringContentReader):
	"""Expose a Content-Length body as a binary stream without pre-reading."""

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> RequestReader:
		if reader.chunked:
			raise ClientError(
				'Content-Length is required',
				status=411,
			)
		return reader


class ChunkedStreamContentReader(StreamContentReader):
	"""Decode a chunked body as a binary stream that can read client chunks one at a time."""

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> ChunkedStream:
		if not reader.chunked:
			raise ClientError('Chunked transfer encoding is required')
		return ChunkedStream(reader)


class TextContentReader(ByteStringContentReader):
	"""Decode text/* bodies into strings."""

	def __init__(
		self,
		va: Union[Validator, Pattern, None] = None,
		error: Optional[Error] = None,
		typeerror: Optional[Error] = None,
	):
		super().__init__(
			va=va,
			error=error,
		)
		self.typeerror = typeerror
		return

	def accepts(
		self,
		format: str,
	) -> bool:
		return format.startswith('text/')

	def __call__(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		format = request.format
		if format is None or not self.accepts(format):
			raise self.typeerror if self.typeerror is not None else ClientError(
				'Unsupported body format',
				status=415,
			)
		return super().__call__(
			request,
			reader,
		)

	def decode(
		self,
		request: Request,
		reader: RequestReader,
	) -> str:
		try:
			return reader.read().decode(request.charset or 'utf-8')
		except (UnicodeError, LookupError) as error:
			raise ClientError('Invalid body character encoding') from error

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		return self.validate(self.decode(
			request,
			reader,
		))


class FormUrlEncodedContentReader(TextContentReader):
	"""Read URL-encoded forms with single or multiple values."""

	def accepts(
		self,
		format: str,
	) -> bool:
		return format == 'application/x-www-form-urlencoded'

	def read_content(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
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
	"""Read JSON bodies with optional value conversion and validation."""

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

	def accepts(
		self,
		format: str,
	) -> bool:
		return format == 'application/json'

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
		try:
			value = loads(self.decode(
				request,
				reader,
			))
		except ValueError as error:
			raise ClientError('Invalid JSON body') from error
		if self.typereader is not None:
			value = self.convert(value)
		return self.validate(value)
