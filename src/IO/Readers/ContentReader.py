from abc import (
	ABC,
	abstractmethod,
)
from typing import Any

from ...Request import Request
from ..RequestReader import RequestReader


class ContentReader(ABC):
	"""Define body parsing and streaming input selection."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		reader: RequestReader,
	) -> Any:
		raise NotImplementedError


class TypeReader(ABC):
	"""Define conversion of individual JSON leaf values."""

	@abstractmethod
	def __call__(
		self,
		value: Any,
	) -> Any:
		raise NotImplementedError
