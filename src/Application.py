from abc import (
	ABC,
	abstractmethod,
)
from dataclasses import dataclass
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
from weakref import ref

from .Error import ClientError
from .RequestRunner import RequestRunner
from .Request import Request
from .Response import (
	Response,
	close_bodies,
)
from .Route import Route
from .Router import Router
from .Runners import RunRequest
from .Utils.Loader import Loader
from .Runners.RunOptions import RunOptions
from .Extension import Extension

__all__ = (
	'Application',
	'ApplicationStartup',
	'ApplicationCleanup',
	'ApplicationRequest',
	'ApplicationRequestResponse',
	'ApplicationRequestError',
	'RequestHookRegistration',
)


class ApplicationStartup(ABC):
	"""Define the call contract for application startup hooks."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ApplicationCleanup(ABC):
	"""Define the call contract for application cleanup hooks."""

	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class ApplicationRequest(ABC):
	"""Define the call contract for request-entry hooks."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Request:
		raise NotImplementedError


class ApplicationRequestResponse(ABC):
	"""Define the call contract for response-return hooks."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		raise NotImplementedError


class ApplicationRequestError(ABC):
	"""Define the call contract for request-error hooks."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> Optional[Response]:
		raise NotImplementedError


@dataclass(frozen=True, eq=False)
class RequestHookRegistration:
	"""Provide a token for unregistering request hooks registered during startup."""

	owner: Extension
	request: tuple[ApplicationRequest, ...]
	response: tuple[ApplicationRequestResponse, ...]
	error: tuple[ApplicationRequestError, ...]


Hook = TypeVar(
	'Hook',
)
HookResult = TypeVar(
	'HookResult',
)
EXTENSION_OWNERS: dict[int, tuple[ref[Extension], ref['Application']]] = {}
EXTENSION_OWNERS_LOCK = RLock()


def forget_extension(
	identity: int,
	reference: ref[Extension],
) -> None:
	with EXTENSION_OWNERS_LOCK:
		owner = EXTENSION_OWNERS.get(identity)
		if owner is not None and owner[0] is reference:
			del EXTENSION_OWNERS[identity]
	return


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

	logger = getLogger('Application')

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
		self.extension_routes: list[Route] = []
		if not isinstance(exts, Sequence) or isinstance(exts, (str, bytes)):
			raise TypeError('exts must be a sequence of Extension instances')
		self.exts = tuple(exts)
		if not all(isinstance(extension, Extension) for extension in self.exts):
			raise TypeError('exts must contain Extension instances')
		if len({id(extension) for extension in self.exts}) != len(self.exts):
			raise ValueError('Extension instances cannot be registered more than once')
		with EXTENSION_OWNERS_LOCK:
			for extension in self.exts:
				owner = EXTENSION_OWNERS.get(id(extension))
				if owner is not None and owner[0]() is extension and owner[1]() is not None:
					raise ValueError('Extension instances cannot be shared between Applications')
			for extension in self.exts:
				identity = id(extension)
				EXTENSION_OWNERS[identity] = (
					ref(
						extension,
						lambda reference, key=identity: forget_extension(
							key,
							reference,
						),
					),
					ref(self),
				)
		self.running = False
		self.lifecycle_lock = RLock()
		self.lifecycle_transition = False
		self.current_extension: Optional[Extension] = None
		self.started_extensions: list[Extension] = []
		self.request_hook_registrations: list[RequestHookRegistration] = []
		return

	def start(self) -> None:
		"""Bind and start registered extensions in order after application startup hooks."""
		self.ensure_not_in_hook()
		with self.lifecycle_lock:
			if self.running or self.lifecycle_transition:
				raise RuntimeError('Application is already running')
			self.lifecycle_transition = True
			self.started_extensions.clear()
			previous_routes = tuple(
				route for route in self.router.routes
				if route not in self.extension_routes
			)
			self.router.routes[:] = previous_routes
			self.extension_routes.clear()
			previous_hooks = tuple(self.request_hook_registrations)
			self.logger.info('Application starting: extensions=%s', len(self.exts))
			try:
				self.run_hooks(self.startup_hooks)
				for extension in self.exts:
					self.current_extension = extension
					self.logger.debug('Extension starting: extension=%s', type(extension).__qualname__)
					if extension.startup(self) is not None:
						raise TypeError('Extension.startup must return None')
					self.logger.debug('Extension started: extension=%s', type(extension).__qualname__)
					self.started_extensions.append(extension)
			except Exception:
				self.logger.exception('Application startup failed')
				for extension in reversed(self.started_extensions):
					self.current_extension = extension
					try:
						self.logger.debug('Extension rolling back: extension=%s', type(extension).__qualname__)
						if extension.cleanup() is not None:
							raise TypeError('Extension.cleanup must return None')
						self.logger.debug('Extension rolled back: extension=%s', type(extension).__qualname__)
					except Exception:
						self.logger.exception(
							'Cleanup failed after extension startup failure: extension=%s',
							type(extension).__qualname__,
						)
				self.router.routes[:] = previous_routes
				self.extension_routes.clear()
				self.started_extensions.clear()
				self.request_hook_registrations[:] = previous_hooks
				raise
			else:
				self.running = True
				self.logger.info('Application started: extensions=%s', len(self.started_extensions))
			finally:
				self.current_extension = None
				self.lifecycle_transition = False
		return

	def stop(self) -> None:
		"""Clean up started extensions in reverse order and raise the first error after all attempts."""
		self.ensure_not_in_hook()
		with self.lifecycle_lock:
			if self.lifecycle_transition:
				raise RuntimeError('Application lifecycle transition is already in progress')
			if not self.running:
				return
			self.running = False
			self.lifecycle_transition = True
			self.logger.info('Application stopping: extensions=%s', len(self.started_extensions))
			first_error = None
			try:
				for extension in reversed(self.started_extensions):
					self.current_extension = extension
					try:
						self.logger.debug('Extension cleaning up: extension=%s', type(extension).__qualname__)
						if extension.cleanup() is not None:
							raise TypeError('Extension.cleanup must return None')
						self.logger.debug('Extension cleaned up: extension=%s', type(extension).__qualname__)
					except Exception as error:
						self.logger.exception('Extension shutdown failed: extension=%s', type(extension).__qualname__)
						if first_error is None:
							first_error = error
					finally:
						self.request_hook_registrations[:] = [
							record for record in self.request_hook_registrations
							if record.owner is not extension
						]
				self.current_extension = None
				try:
					self.run_hooks(self.cleanup_hooks)
				except Exception as error:
					self.logger.exception('Application cleanup failed')
					if first_error is None:
						first_error = error
			finally:
				self.current_extension = None
				self.started_extensions.clear()
				self.lifecycle_transition = False
			if first_error is not None:
				raise first_error
			self.logger.info('Application stopped')
		return

	def add_extension_route(
		self,
		extension: Extension,
		route: Route,
	) -> None:
		"""Validate and register a route owned by the extension currently starting."""
		self.ensure_not_in_hook()
		with self.lifecycle_lock:
			if (
				self.running
				or not self.lifecycle_transition
				or self.current_extension is not extension
				or any(started is extension for started in self.started_extensions)
			):
				raise RuntimeError('Extension routes can only be registered during their startup')
			if not isinstance(route, Route):
				raise TypeError('A Route instance is required')
			if (
				not isinstance(route.object, type)
				or not issubclass(route.object, RequestRunner)
				or isabstract(route.object)
			):
				raise TypeError('Extension routes require concrete RequestRunner classes')
			if any(
				entry.method == route.method and entry.url == route.url
				for entry in self.router.routes
			):
				raise ValueError('Extension route already registered: ' + route.method + ' ' + route.url)
			self.router.add(route)
			self.extension_routes.append(route)
			self.logger.debug(
				'Extension route registered: extension=%s method=%s route=%s',
				type(extension).__qualname__,
				route.method,
				ascii(route.url[:256]),
			)
		return

	def add_request_hooks(
		self,
		*,
		on_request: Union[ApplicationRequest, Sequence[ApplicationRequest]] = (),
		on_request_response: Union[
			ApplicationRequestResponse,
			Sequence[ApplicationRequestResponse],
		] = (),
		on_request_error: Union[
			ApplicationRequestError,
			Sequence[ApplicationRequestError],
		] = (),
	) -> RequestHookRegistration:
		"""Register request hooks during extension startup, before constructor hooks."""
		self.ensure_not_in_hook()
		with self.lifecycle_lock:
			owner = self.current_extension
			if (
				self.running
				or not self.lifecycle_transition
				or owner is None
				or any(started is owner for started in self.started_extensions)
			):
				raise RuntimeError('Request hooks can only be registered during extension startup')
			registration = RequestHookRegistration(
				owner,
				application_hooks(on_request, ApplicationRequest, 'on_request'),
				application_hooks(on_request_response, ApplicationRequestResponse, 'on_request_response'),
				application_hooks(on_request_error, ApplicationRequestError, 'on_request_error'),
			)
			if not (registration.request or registration.response or registration.error):
				raise ValueError('At least one request hook is required')
			for incoming, configured in (
				(
					registration.request,
					self.request_hooks,
				),
				(
					registration.response,
					self.request_response_hooks,
				),
				(
					registration.error,
					self.request_error_hooks,
				),
			):
				if len({id(hook) for hook in incoming}) != len(incoming) or any(
					first is second for first in configured for second in incoming
				):
					raise ValueError('Request hook instance is already registered')
			for existing in self.request_hook_registrations:
				for previous, incoming in (
					(
						existing.request,
						registration.request,
					),
					(
						existing.response,
						registration.response,
					),
					(
						existing.error,
						registration.error,
					),
				):
					if any(first is second for first in previous for second in incoming):
						raise ValueError('Request hook instance is already registered')
			self.request_hook_registrations.append(registration)
			self.logger.debug(
				'Request hooks registered: extension=%s request=%s response=%s error=%s',
				type(registration.owner).__qualname__,
				len(registration.request),
				len(registration.response),
				len(registration.error),
			)
			return registration

	def remove_request_hooks(
		self,
		registration: RequestHookRegistration,
	) -> None:
		"""Unregister request hooks using a token during the owning extension's startup or cleanup."""
		self.ensure_not_in_hook()
		with self.lifecycle_lock:
			if self.running or not self.lifecycle_transition or self.current_extension is None:
				raise RuntimeError('Request hooks can only be removed during extension startup or cleanup')
			if not isinstance(registration, RequestHookRegistration):
				raise TypeError('A RequestHookRegistration token is required')
			if registration.owner is not self.current_extension:
				raise ValueError('Request hooks belong to another Extension')
			if not any(record is registration for record in self.request_hook_registrations):
				raise ValueError('Request hook registration is not active')
			self.request_hook_registrations.remove(registration)
			self.logger.debug('Request hooks removed: extension=%s', type(registration.owner).__qualname__)
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
		for index, hook in enumerate(hooks):
			self.logger.debug('Application lifecycle hook starting: index=%s hook=%s', index, type(hook).__qualname__)
			result = self.invoke_hook(
				hook,
				*args,
			)
			if result is not None:
				raise TypeError('Lifecycle hooks must return None')
			self.logger.debug('Application lifecycle hook completed: index=%s', index)
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
		if self.running or self.lifecycle_transition:
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
		self.logger.debug(
			'Handler registered: method=%s route=%s handler=%s',
			properties.method,
			ascii(properties.url[:256]),
			handler.__module__ + '.' + handler.__qualname__,
		)
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
			self.logger.debug('Module loaded: module=%s', module.__name__)
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
		self.logger.debug('Application request received: request_id=%s method=%s', request.id, ascii(request.method[:32]))
		request_id = request.id

		def dispatch() -> Optional[Response]:
			if request.method == 'OPTIONS' and request.uri == '*':
				self.logger.debug('OPTIONS wildcard selected: request_id=%s', request.id)
				return RunOptions().run(
					request,
					self.router,
				)
			matches = self.router.matches(request.path)
			if not matches:
				self.logger.debug('Route not found: request_id=%s', request.id)
				raise ClientError(
					'No matching route',
					status=404,
				)
			if request.method == 'OPTIONS' and 'OPTIONS' not in matches:
				self.logger.debug('Automatic OPTIONS selected: request_id=%s', request.id)
				return RunOptions().run(
					request,
					self.router,
				)
			if request.method not in matches:
				self.logger.debug('Method not allowed: request_id=%s', request.id)
				raise ClientError(
					'Method not allowed',
					status=405,
				)
			route, parameters = matches[request.method]
			self.logger.debug(
				'Route selected: request_id=%s method=%s route=%s handler=%s',
				request.id,
				ascii(request.method[:32]),
				ascii(route.url[:256]),
				route.object.__module__ + '.' + route.object.__qualname__,
			)
			if (request.reader.chunked or request.reader.remaining) and request.format is None:
				raise ClientError('Content-Type is required for requests with a body')
			if (request.reader.chunked or request.reader.remaining) and route.object.properties.body is None:
				raise ClientError(
					'No body reader is configured for this handler',
					status=415,
				)
			request.params = parameters
			return RunRequest(route.object).run(request)

		with self.lifecycle_lock:
			registrations = tuple(self.request_hook_registrations)
			request_hooks = tuple(
				hook for registration in registrations for hook in registration.request
			) + self.request_hooks
			response_hooks = tuple(
				hook for registration in registrations for hook in registration.response
			) + self.request_response_hooks
			error_hooks = tuple(
				hook for registration in registrations for hook in registration.error
			) + self.request_error_hooks
		previous_request = getattr(self.hook_context, 'request', None)
		self.hook_context.request = request
		try:
			for index, hook in enumerate(request_hooks):
				previous_id = request.id
				self.logger.debug('Application request hook starting: request_id=%s index=%s hook=%s', request.id, index, type(hook).__qualname__)
				request = self.invoke_hook(
					hook,
					request,
				)
				if not isinstance(request, Request):
					raise TypeError('ApplicationRequest hooks must return a Request')
				self.logger.debug('Application request hook completed: request_id=%s index=%s', request.id, index)
				if previous_id != request.id:
					self.logger.debug('Request replaced: previous_request_id=%s request_id=%s', previous_id, request.id)
			self.logger.debug('Application dispatch starting: request_id=%s', request.id)
			response = dispatch()
			self.logger.debug('Application dispatch completed: request_id=%s', request.id)
			for index, hook in enumerate(response_hooks):
				previous = response
				previous_body = previous.body if previous is not None else None
				self.logger.debug('Application response hook starting: request_id=%s index=%s hook=%s', request.id, index, type(hook).__qualname__)
				try:
					result = self.invoke_hook(
						hook,
						request,
						response,
					)
					if result is not None and not isinstance(result, Response):
						raise TypeError('ApplicationRequestResponse hooks must return a Response or None')
					if previous is None and result is not None:
						raise TypeError('ApplicationRequestResponse hooks cannot replace direct output')
				except Exception:
					if previous is not None:
						close_bodies(
							previous_body,
							previous.body,
							preserve_error=True,
						)
					raise
				response = result
				if previous is not None:
					try:
						close_bodies(*(
							body for body in (
								previous_body,
								previous.body,
							)
							if response is None or body is not response.body
						))
					except Exception:
						if response is not None:
							close_bodies(
								response.body,
								preserve_error=True,
							)
						raise
				self.logger.debug('Application response hook completed: request_id=%s index=%s', request.id, index)
			self.logger.debug(
				'Application response provided: request_id=%s mode=%s',
				request.id,
				'returned' if response is not None else 'direct',
			)
			return response
		except Exception as error:
			self.logger.debug(
				'Application request failed: request_id=%s error_type=%s',
				request_id,
				type(error).__qualname__,
			)
			for index, hook in enumerate(error_hooks):
				self.logger.debug(
					'Application error hook starting: request_id=%s index=%s hook=%s',
					request.id if isinstance(request, Request) else request_id,
					index,
					type(hook).__qualname__,
				)
				result = self.invoke_hook(
					hook,
					request,
					error,
				)
				if result is not None and not isinstance(result, Response):
					raise TypeError('ApplicationRequestError hooks must return a Response or None')
				if result is not None:
					writer = request.response_writer if isinstance(request, Request) else None
					if writer is not None and writer.started:
						close_bodies(
							result.body,
							preserve_error=True,
						)
						raise RuntimeError('Cannot return a Response after starting direct output')
					return result
				self.logger.debug('Application error hook completed: request_id=%s index=%s', request_id, index)
			raise
		finally:
			self.hook_context.request = previous_request
