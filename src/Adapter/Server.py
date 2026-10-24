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

__all__ = (
	'Server',
)


ServerType = TypeVar(
	'ServerType',
	bound='Server',
)


class Server(ABC):
	"""Define the server adapter contract for running an application at an address."""

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
		"""Return this instance without starting the server."""
		return self

	def __exit__(
		self,
		exception_type: Optional[type[BaseException]],
		exception: Optional[BaseException],
		traceback: Optional[TracebackType],
	) -> None:
		"""Propagate exceptions; run() is responsible for cleaning up active resources."""
		return

	@abstractmethod
	def run(self) -> None:
		"""Serve until shutdown and manage the application lifecycle."""
		raise NotImplementedError
