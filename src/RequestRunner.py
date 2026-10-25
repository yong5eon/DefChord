from abc import (
	ABC,
	ABCMeta,
	abstractmethod,
)
from dataclasses import dataclass
from re import fullmatch
from typing import (
	Mapping,
	Optional,
	Sequence,
	Type,
	TypeVar,
	Union,
)

from .Body import Body
from .Request import Request
from .Response import Response
from .ResponseSpecification import ResponseSpecification
from .Validators import (
	Auth,
	Headers,
	Origin,
	Parameters,
	QueryString,
)

__all__ = (
	'RequestRunnerRequest',
	'RequestRunnerRequestResponse',
	'RequestRunnerRequestError',
	'RequestProperties',
	'RequestRunner',
)


class RequestRunnerRequest(ABC):
	"""Transform a prepared request immediately before the handler runs."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Request:
		raise NotImplementedError


class RequestRunnerRequestResponse(ABC):
	"""Transform a returned response or a direct-output response before transmission."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		response: Response,
	) -> Response:
		raise NotImplementedError


class RequestRunnerRequestError(ABC):
	"""Observe execution errors from validation through response processing."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> Optional[Response]:
		raise NotImplementedError


Hook = TypeVar('Hook')


def request_runner_hooks(
	value: Union[Hook, Sequence[Hook], None],
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


def require_contract(
	value: object,
	contract: Type,
	name: str,
	*,
	multiple: bool = False,
) -> None:
	if value is None:
		return
	values = (value,) if isinstance(value, contract) else value
	if multiple:
		if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
			raise TypeError(name + ' must contain ' + contract.__name__ + ' instances')
		if any(not isinstance(item, contract) for item in values):
			raise TypeError(name + ' must contain ' + contract.__name__ + ' instances')
		return
	if not isinstance(value, contract):
		raise TypeError(name + ' must be a ' + contract.__name__ + ' instance')
	return


class RequestRunnerMeta(ABCMeta):
	def __new__(
		cls,
		class_name,
		bases,
		namespace,
		**kwargs,
	):
		if 'name' in kwargs:
			if 'request_runner_name' in kwargs:
				raise TypeError('Specify only one request runner name')
			kwargs['request_runner_name'] = kwargs.pop('name')
		return super().__new__(
			cls,
			class_name,
			bases,
			namespace,
			**kwargs,
		)


@dataclass(frozen=True)
class RequestProperties:
	"""Store request handler settings for registration with an application."""

	method: Optional[str]
	url: Optional[str]
	origin: Union[Origin, Sequence[Origin], None]
	auth: Optional[Auth]
	parameters: Optional[Parameters]
	qs: Optional[QueryString]
	headers: Optional[Headers]
	body: Optional[Body]
	response: Union[
		ResponseSpecification,
		Mapping[str, Union[str, Mapping[str, object]]],
		Sequence[ResponseSpecification],
		None,
	]
	summary: Optional[str]
	description: Optional[str]
	tags: Union[str, Sequence[str], None]
	on_request: tuple[RequestRunnerRequest, ...]
	on_request_response: tuple[RequestRunnerRequestResponse, ...]
	on_request_error: tuple[RequestRunnerRequestError, ...]
	name: Optional[str] = None


class RequestRunner(
	ABC,
	metaclass=RequestRunnerMeta,
):
	"""Configure a handler through class declarations and instantiate it per request."""

	properties: RequestProperties

	def __init_subclass__(
		cls,
		*,
		method: Optional[str] = None,
		url: Optional[str] = None,
		request_runner_name: Optional[str] = None,
		origin: Union[Origin, Sequence[Origin], None] = None,
		auth: Optional[Auth] = None,
		parameters: Optional[Parameters] = None,
		qs: Optional[QueryString] = None,
		headers: Optional[Headers] = None,
		body: Optional[Body] = None,
		response: Union[
			ResponseSpecification,
			Mapping[str, Union[str, Mapping[str, object]]],
			Sequence[ResponseSpecification],
			None,
		] = None,
		summary: Optional[str] = None,
		description: Optional[str] = None,
		tags: Union[str, Sequence[str], None] = None,
		on_request: Union[
			RequestRunnerRequest,
			Sequence[RequestRunnerRequest],
			None,
		] = None,
		on_request_response: Union[
			RequestRunnerRequestResponse,
			Sequence[RequestRunnerRequestResponse],
			None,
		] = None,
		on_request_error: Union[
			RequestRunnerRequestError,
			Sequence[RequestRunnerRequestError],
			None,
		] = None,
	):
		super().__init_subclass__()
		if request_runner_name is not None and (
			not isinstance(request_runner_name, str) or not request_runner_name.strip()
		):
			raise ValueError('name must be a non-empty string')
		if (method is None) != (url is None):
			raise TypeError('method and url must be specified together')
		if method is not None and fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", method) is None:
			raise ValueError('Invalid HTTP method token')
		if url is not None and (not url.startswith('/') or '?' in url or '#' in url):
			raise ValueError('url must be a path starting with /')
		require_contract(origin, Origin, 'origin', multiple=True)
		require_contract(auth, Auth, 'auth')
		require_contract(parameters, Parameters, 'parameters')
		require_contract(qs, QueryString, 'qs')
		require_contract(headers, Headers, 'headers')
		require_contract(body, Body, 'body')
		cls.properties = RequestProperties(
			method=method,
			url=url,
			name=request_runner_name,
			origin=origin,
			auth=auth,
			parameters=parameters,
			qs=qs,
			headers=headers,
			body=body,
			response=response,
			summary=summary,
			description=description,
			tags=tags,
			on_request=request_runner_hooks(
				on_request,
				RequestRunnerRequest,
				'on_request',
			),
			on_request_response=request_runner_hooks(
				on_request_response,
				RequestRunnerRequestResponse,
				'on_request_response',
			),
			on_request_error=request_runner_hooks(
				on_request_error,
				RequestRunnerRequestError,
				'on_request_error',
			),
		)
		return

	@abstractmethod
	def run(
		self,
		request: Request,
	) -> Optional[Response]:
		"""Return a Response, or write through request.writer and return None."""
		raise NotImplementedError
