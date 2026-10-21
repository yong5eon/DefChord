from abc import (
	ABC,
	abstractmethod,
)
from typing import (
	Optional,
	TYPE_CHECKING,
)

from .Request import Request
from .Response import Response

if TYPE_CHECKING:
	from .Application import Application


class Extension(ABC):
	"""Application 하나에 귀속되는 HTTP 확장과 관찰 계약."""

	methods = (
		'GET',
		'HEAD',
	)

	def __init__(
		self,
		path: str,
	):
		if not isinstance(path, str) or not path.startswith('/') or any(
			character in path for character in (
				'?',
				'#',
				':',
			)
		):
			raise ValueError('확장에는 매개변수 없는 절대 HTTP 경로가 필요합니다')
		self.path = path
		self.application: Optional['Application'] = None
		return

	def bind(
		self,
		app: 'Application',
	) -> None:
		"""전체 확장 등록 후 의존성을 확인한다."""
		return

	def start(
		self,
		app: 'Application',
	) -> None:
		return

	def stop(
		self,
		app: 'Application',
	) -> None:
		return

	def begin(
		self,
		request: Request,
	) -> object:
		return None

	def end(
		self,
		request: Request,
		context: object,
		status: int,
		error: Optional[BaseException],
	) -> None:
		return

	@abstractmethod
	def handle(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		raise NotImplementedError
