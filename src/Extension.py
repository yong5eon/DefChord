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
	"""Define HTTP extension and observation hooks owned by one Application."""

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
			raise ValueError('Extensions require an absolute HTTP path without parameters')
		self.path = path
		self.application: Optional['Application'] = None
		return

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
	def handle(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		raise NotImplementedError
