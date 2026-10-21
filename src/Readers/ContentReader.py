from abc import (
	ABC,
	abstractmethod,
)
from typing import Any

from ..Request import Request
from ..RequestReader import RequestReader


class ContentReader(ABC):
	"""일반 본문 해석과 스트림 입력을 선택하는 읽기 계약."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		raise NotImplementedError


class TypeReader(ABC):
	"""JSON의 각 말단 값을 변환하는 확장 계약."""

	@abstractmethod
	def __call__(
		self,
		value: Any,
	) -> Any:
		raise NotImplementedError
