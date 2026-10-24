from abc import (
	ABC,
	abstractmethod,
)
from inspect import isabstract
from logging import getLogger
from threading import (
	RLock,
	local,
)
from typing import (
	Callable,
	Optional,
	Sequence,
	Type,
	TypeVar,
	Union,
)

from .Error import ClientError
from .RequestRunner import RequestRunner
from .Request import Request
from .Response import Response
from .Route import Route
from .Router import Router
from .Runners import RunRequest
from .Utils.Loader import Loader
from .Runners.RunOptions import RunOptions
from .Extension import Extension
from .Runners.RunExtension import RunExtensionFactory

__all__ = (
	'Application',
	'ApplicationStartup',
	'ApplicationCleanup',
	'ApplicationRequest',
	'ApplicationRequestResponse',
	'ApplicationRequestError',
)


class ApplicationStartup(ABC):
	"""애플리케이션 시작 훅의 호출 계약."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ApplicationCleanup(ABC):
	"""애플리케이션 정리 훅의 호출 계약."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ApplicationRequest(ABC):
	"""요청 처리 진입 훅의 호출 계약."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Request:
		raise NotImplementedError


class ApplicationRequestResponse(ABC):
	"""요청 응답 반환 훅의 호출 계약."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		raise NotImplementedError


class ApplicationRequestError(ABC):
	"""요청 처리 오류 훅의 호출 계약."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> None:
		raise NotImplementedError


Hook = TypeVar(
	'Hook',
)
HookResult = TypeVar(
	'HookResult',
)


def application_hooks(
	value: Union[Hook, Sequence[Hook]],
	contract: Type[Hook],
	name: str,
) -> tuple[Hook, ...]:
	if isinstance(value, contract):
		return (value,)
	if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
		result = tuple(value)
		if all(isinstance(hook, contract) for hook in result):
			return result
	raise TypeError(name + ' must be a ' + contract.__name__ + ' instance or a sequence of them')


class Application:
	"""Own registration state and execute a new handler instance per request."""

	def __init__(
		self,
		exts: Sequence[Extension] = (),
		*,
		on_startup: Union[ApplicationStartup, Sequence[ApplicationStartup]] = (),
		on_cleanup: Union[ApplicationCleanup, Sequence[ApplicationCleanup]] = (),
		on_request: Union[ApplicationRequest, Sequence[ApplicationRequest]] = (),
		on_request_response: Union[
			ApplicationRequestResponse,
			Sequence[ApplicationRequestResponse],
		] = (),
		on_request_error: Union[
			ApplicationRequestError,
			Sequence[ApplicationRequestError],
		] = (),
	):
		self.startup_hooks = application_hooks(
			on_startup,
			ApplicationStartup,
			'on_startup',
		)
		self.cleanup_hooks = application_hooks(
			on_cleanup,
			ApplicationCleanup,
			'on_cleanup',
		)
		self.request_hooks = application_hooks(
			on_request,
			ApplicationRequest,
			'on_request',
		)
		self.request_response_hooks = application_hooks(
			on_request_response,
			ApplicationRequestResponse,
			'on_request_response',
		)
		self.request_error_hooks = application_hooks(
			on_request_error,
			ApplicationRequestError,
			'on_request_error',
		)
		self.hook_context = local()
		self.router = Router()
		self.exts: dict[str, Extension] = {}
		self.running = False
		self.lifecycle_lock = RLock()
		extensions = tuple(exts)
		for extension in extensions:
			if not isinstance(extension, Extension):
				raise TypeError('exts must contain Extension instances')
			if extension.application is not None:
				raise ValueError('Extension instances cannot be shared between Applications')
			if extension.path in self.exts:
				raise ValueError('Duplicate extension path: ' + extension.path)
			self.exts[extension.path] = extension
		try:
			for extension in extensions:
				for method in extension.methods:
					handler = RunExtensionFactory(
						self,
						extension,
						method,
					)()
					self.router.add(extension.route(
						method,
						handler,
					))
			for extension in extensions:
				extension.bind(self)
		except Exception:
			self.exts.clear()
			raise
		for extension in extensions:
			extension.application = self
		return

	def start(self) -> None:
		"""Start extensions in declaration order before serving requests."""
		self.ensure_not_in_hook()
		with self.lifecycle_lock:
			if self.running:
				raise RuntimeError('Application is already running')
			self.run_hooks(self.startup_hooks)
			started = []
			try:
				for extension in self.exts.values():
					extension.start(self)
					started.append(extension)
			except Exception:
				for extension in reversed(started):
					try:
						extension.stop(self)
					except Exception:
						getLogger('DefEssential.Application').exception('Cleanup failed after extension startup failure')
				raise
			self.running = True
		return

	def stop(self) -> None:
		"""Stop started extensions in reverse order and propagate cleanup errors."""
		self.ensure_not_in_hook()
		with self.lifecycle_lock:
			if not self.running:
				return
			self.running = False
			first_error = None
			for extension in reversed(tuple(self.exts.values())):
				try:
					extension.stop(self)
				except Exception as error:
					getLogger('DefEssential.Application').exception('Extension shutdown failed')
					if first_error is None:
						first_error = error
			try:
				self.run_hooks(self.cleanup_hooks)
			except Exception as error:
				getLogger('DefEssential.Application').exception('Application cleanup failed')
				if first_error is None:
					first_error = error
			if first_error is not None:
				raise first_error
		return

	def ensure_not_in_hook(self) -> None:
		if getattr(self.hook_context, 'active', False):
			raise RuntimeError('Application methods cannot be called from an Application hook')
		return

	def run_hooks(
		self,
		hooks: Sequence[Callable[..., object]],
		*args: object,
	) -> None:
		for hook in hooks:
			result = self.invoke_hook(
				hook,
				*args,
			)
			if result is not None:
				raise TypeError('Application startup and cleanup hooks must return None')
		return

	def invoke_hook(
		self,
		hook: Callable[..., HookResult],
		*args: object,
	) -> HookResult:
		active = getattr(self.hook_context, 'active', False)
		self.hook_context.active = True
		try:
			return hook(*args)
		finally:
			self.hook_context.active = active

	def add(
		self,
		handler: Type[RequestRunner],
	) -> None:
		if self.running:
			raise RuntimeError('Cannot add handlers while Application is running')
		if not issubclass(
			handler,
			RequestRunner,
		) or isabstract(handler):
			raise TypeError('A concrete RequestRunner class is required')
		properties = handler.properties
		if properties.method is None or properties.url is None:
			raise ValueError('Handlers must define method and url before registration')
		self.router.add(Route(
			properties.method,
			properties.url,
			handler,
		))
		return

	def load(
		self,
		mod: Optional[str] = None,
		path: Optional[str] = None,
	) -> None:
		"""Register modules independently for each Application, even if already imported."""
		for module in Loader()(
			mod=mod,
			path=path,
		):
			for value in vars(module).values():
				if (
					isinstance(value, type)
					and issubclass(value, RequestRunner)
					and value is not RequestRunner
					and value.__module__ == module.__name__
					and not isabstract(value)
				):
					self.add(value)
		return

	def __call__(
		self,
		request: Request,
	) -> Optional[Response]:
		self.ensure_not_in_hook()

		def dispatch() -> Optional[Response]:
			if request.method == 'OPTIONS' and request.uri == '*':
				return RunOptions().run(
					request,
					self.router,
				)
			matches = self.router.matches(request.path)
			if not matches:
				raise ClientError(
					'No matching route',
					status=404,
				)
			if request.method == 'OPTIONS' and 'OPTIONS' not in matches:
				return RunOptions().run(
					request,
					self.router,
				)
			if request.method not in matches:
				raise ClientError(
					'Method not allowed',
					status=405,
				)
			if (request.reader.chunked or request.reader.remaining) and request.format is None:
				raise ClientError('Content-Type is required for requests with a body')
			route, parameters = matches[request.method]
			if (request.reader.chunked or request.reader.remaining) and route.object.properties.body is None:
				raise ClientError(
					'No body reader is configured for this handler',
					status=415,
				)
			request.params = parameters
			return RunRequest(route.object).run(request)

		try:
			for hook in self.request_hooks:
				request = self.invoke_hook(
					hook,
					request,
				)
				if not isinstance(request, Request):
					raise TypeError('ApplicationRequest hooks must return a Request')
			response = dispatch()
			for hook in self.request_response_hooks:
				previous = response
				response = self.invoke_hook(
					hook,
					request,
					response,
				)
				if response is not None and not isinstance(response, Response):
					raise TypeError('ApplicationRequestResponse hooks must return a Response or None')
				if previous is None and response is not None:
					raise TypeError('ApplicationRequestResponse hooks cannot replace direct output')
			return response
		except Exception as error:
			for hook in self.request_error_hooks:
				result = self.invoke_hook(
					hook,
					request,
					error,
				)
				if result is not None:
					raise TypeError('ApplicationRequestError hooks must return None')
			raise
