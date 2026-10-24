from abc import (
	ABC,
	abstractmethod,
)
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
	"""확장 시작 훅의 호출 계약."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ExtensionCleanup(ABC):
	"""확장 정리 훅의 호출 계약."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ExtensionRequest(ABC):
	"""확장 요청 진입 훅의 호출 계약."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Request:
		raise NotImplementedError


class ExtensionRequestResponse(ABC):
	"""확장 응답 반환 훅의 호출 계약."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		raise NotImplementedError


class ExtensionRequestError(ABC):
	"""확장 오류 관찰 훅의 호출 계약."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> None:
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
	"""인스턴스별 사용자 훅과 시작·요청·정리 계약을 제공한다."""

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
		"""구현체 준비 후 호출하여 사용자 시작 훅을 실행한다."""
		for hook in self.startup_hooks:
			if hook() is not None:
				raise TypeError('ExtensionStartup hooks must return None')
		return

	def cleanup(self) -> None:
		"""사용자 정리 훅을 실행한다. 구현체는 별도로 자원 회수를 보장한다."""
		for hook in self.cleanup_hooks:
			if hook() is not None:
				raise TypeError('ExtensionCleanup hooks must return None')
		return

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Optional[Response]:
		raise NotImplementedError
