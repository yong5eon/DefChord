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
	"""설정을 보관하고 호출 시 등록할 요청 처리 대상을 생성한다."""

	@abstractmethod
	def __call__(self) -> T:
		raise NotImplementedError
