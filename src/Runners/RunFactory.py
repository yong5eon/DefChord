from abc import (
	ABC,
	abstractmethod,
)
from typing import (
	Generic,
	TypeVar,
)

__all__ = (
	'RunFactory',
)


T = TypeVar('T')


class RunFactory(
	ABC,
	Generic[T],
):
	"""Store configuration and create a request handler to register when called."""

	@abstractmethod
	def __call__(self) -> T:
		raise NotImplementedError
