from .Readers import ContentReader
from .Error import ClientError
from .Request import Request
from .Content import Content
from typing import (
	Sequence,
	Union,
)


class Body:
	"""본문의 필수 여부와 명시적으로 선택한 읽기 방식을 적용한다."""

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
				raise ClientError('필수 요청 본문이 없습니다')
			return None
		if request.header('Content-Type') is None:
			raise ClientError('본문이 있는 요청에는 Content-Type이 필요합니다')
		if self.content and request.format not in (
			content.format.lower() for content in self.content
		):
			raise ClientError(
				'지원하지 않는 본문 형식',
				status=415,
			)
		return self.reader(
			request,
			request.reader,
		)
