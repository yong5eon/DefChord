from .IO.Readers import ContentReader
from .Error import ClientError
from .Request import Request
from .Content import Content
from typing import (
	Sequence,
	Union,
)


class Body:
	"""Apply body requirements and the explicitly selected reader."""

	def __init__(
		self,
		reader: ContentReader,
		content: Union[Content, Sequence[Content], None] = None,
		required: bool = True,
	):
		self.reader = reader
		self.required = required
		self.content = (content,) if isinstance(content, Content) else tuple(content or ())
		return

	def __call__(
		self,
		request: Request,
	) -> object:
		if request.reader.finished:
			if self.required:
				raise ClientError('Required request body is missing')
			return None
		format = request.format
		if format is None:
			raise ClientError('Content-Type is required for requests with a body')
		if self.content and format not in (
			content.format.lower() for content in self.content
		):
			raise ClientError(
				'Unsupported body format',
				status=415,
			)
		return self.reader(
			request,
			request.reader,
		)
