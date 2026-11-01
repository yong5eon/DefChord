from abc import (
	ABC,
	abstractmethod,
)
from logging import getLogger
from typing import (
	Optional,
	Sequence,
	Type,
	TypeVar,
	TYPE_CHECKING,
	Union,
)

from .Request import Request
from .Response import Response

if TYPE_CHECKING:
	from .Application import Application

__all__ = (
	'Extension',
	'ExtensionStartup',
	'ExtensionCleanup',
	'ExtensionRequest',
	'ExtensionRequestResponse',
	'ExtensionRequestError',
)


class ExtensionStartup(ABC):
	"""Define the call contract for extension startup hooks."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ExtensionCleanup(ABC):
	"""Define the call contract for extension cleanup hooks."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ExtensionRequest(ABC):
	"""Define the call contract for extension request-entry hooks."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Request:
		raise NotImplementedError


class ExtensionRequestResponse(ABC):
	"""Define the call contract for extension response-return hooks."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		raise NotImplementedError


class ExtensionRequestError(ABC):
	"""Define the call contract for extension error-observation hooks."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> Optional[Response]:
		raise NotImplementedError


Hook = TypeVar('Hook')


def extension_hooks(
	value: object,
	contract: Type[Hook],
	name: str,
) -> tuple[Hook, ...]:
	if value is None:
		return ()
	if isinstance(value, contract):
		return (value,)
	if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
		result = tuple(value)
		if all(isinstance(hook, contract) for hook in result):
			return result
	raise TypeError(name + ' must be a ' + contract.__name__ + ' instance or a sequence of them')


class Extension(ABC):
	"""Provide per-instance user hooks and startup, request, and cleanup contracts."""

	logger = getLogger('DefChord.Extension')

	def __init__(
		self,
		*,
		on_startup: Union[
			ExtensionStartup,
			Sequence[ExtensionStartup],
			None,
		] = None,
		on_cleanup: Union[
			ExtensionCleanup,
			Sequence[ExtensionCleanup],
			None,
		] = None,
		on_request: Union[
			ExtensionRequest,
			Sequence[ExtensionRequest],
			None,
		] = None,
		on_request_response: Union[
			ExtensionRequestResponse,
			Sequence[ExtensionRequestResponse],
			None,
		] = None,
		on_request_error: Union[
			ExtensionRequestError,
			Sequence[ExtensionRequestError],
			None,
		] = None,
	) -> None:
		self.startup_hooks = extension_hooks(
			on_startup,
			ExtensionStartup,
			'on_startup',
		)
		self.cleanup_hooks = extension_hooks(
			on_cleanup,
			ExtensionCleanup,
			'on_cleanup',
		)
		self.request_hooks = extension_hooks(
			on_request,
			ExtensionRequest,
			'on_request',
		)
		self.request_response_hooks = extension_hooks(
			on_request_response,
			ExtensionRequestResponse,
			'on_request_response',
		)
		self.request_error_hooks = extension_hooks(
			on_request_error,
			ExtensionRequestError,
			'on_request_error',
		)
		return

	def __str__(self) -> str:
		return type(self).__name__

	def startup(
		self,
		application: 'Application',
	) -> None:
		"""Run user startup hooks after the implementation is ready."""
		for index, hook in enumerate(self.startup_hooks):
			self.logger.debug('Extension startup hook starting: index=%s hook=%s', index, type(hook).__qualname__)
			if hook() is not None:
				raise TypeError('ExtensionStartup hooks must return None')
			self.logger.debug('Extension startup hook completed: index=%s', index)
		return

	def cleanup(self) -> None:
		"""Run user cleanup hooks; the implementation must release its own resources."""
		for index, hook in enumerate(self.cleanup_hooks):
			self.logger.debug('Extension cleanup hook starting: index=%s hook=%s', index, type(hook).__qualname__)
			if hook() is not None:
				raise TypeError('ExtensionCleanup hooks must return None')
			self.logger.debug('Extension cleanup hook completed: index=%s', index)
		return

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Optional[Response]:
		raise NotImplementedError
