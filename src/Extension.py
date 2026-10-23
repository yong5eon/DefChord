from abc import (
	ABC,
	abstractmethod,
)
from typing import (
	Optional,
	Sequence,
	Type,
	TYPE_CHECKING,
	Union,
)

from .Request import Request
from .Response import Response
from .RequestRunner import (
	RequestRunner,
	RequestFilter,
	ResponseFilter,
)
from .Route import Route

__all__ = (
	'Extension',
)

if TYPE_CHECKING:
	from .Application import Application


class Extension(ABC):
	"""Define HTTP extension and observation hooks owned by one Application."""

	methods = (
		'GET',
		'HEAD',
	)

	def __init__(
		self,
		path: str,
		*,
		onRequest: Union[RequestFilter, Sequence[RequestFilter], None] = None,
		onResponse: Union[ResponseFilter, Sequence[ResponseFilter], None] = None,
	):
		if not isinstance(path, str) or not path.startswith('/') or any(
			character in path for character in (
				'?',
				'#',
				':',
			)
		):
			raise ValueError('Extensions require an absolute HTTP path without parameters')
		self.path = path
		self.application: Optional['Application'] = None
		self.on_request = onRequest
		self.on_response = onResponse
		return

	def route(
		self,
		method: str,
		handler: Type[RequestRunner],
	) -> Route:
		"""Create the route used to dispatch this extension."""
		return Route(
			method,
			self.path,
			handler,
		)

	def bind(
		self,
		app: 'Application',
	) -> None:
		"""Validate dependencies after all extensions have been registered."""
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
	def __call__(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		"""애플리케이션과 요청을 받아 확장의 HTTP 응답을 반환한다."""
		raise NotImplementedError
