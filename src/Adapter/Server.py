from abc import (
	ABC,
	abstractmethod,
)
from types import TracebackType
from typing import (
	Optional,
	TypeVar,
)

from ..Application import Application


ServerType = TypeVar(
	'ServerType',
	bound='Server',
)


class Server(ABC):
	"""애플리케이션을 지정한 주소에서 실행하는 서버 어댑터의 계약."""

	def __init__(
		self,
		host: str,
		port: int,
		application: Application,
	):
		self.host = host
		self.port = port
		self.application = application
		return

	def __enter__(self: ServerType) -> ServerType:
		"""서버를 시작하지 않고 같은 인스턴스를 반환한다."""
		return self

	def __exit__(
		self,
		exception_type: Optional[type[BaseException]],
		exception: Optional[BaseException],
		traceback: Optional[TracebackType],
	) -> None:
		"""예외를 전파한다. 실행 중 자원은 run()에서 정리한다."""
		return

	@abstractmethod
	def run(self) -> None:
		"""서버 종료까지 실행하고 애플리케이션 생명주기를 관리한다."""
		raise NotImplementedError
