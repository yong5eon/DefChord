from abc import (
	ABC,
	abstractmethod,
)
from dataclasses import dataclass
from re import fullmatch
from typing import (
	Callable,
	Optional,
	Sequence,
	Union,
)

from .Request import Request
from .Response import Response


RequestCheck = Callable[[Request], None]
RequestFilter = Callable[[Request], tuple[Request, Optional[Response]]]
ResponseFilter = Callable[[Request, Response], Response]


@dataclass(frozen=True)
class RequestProperties:
	"""Store handler settings on the class for Application registration."""

	method: Optional[str]
	url: Optional[str]
	origin: Union[RequestCheck, Sequence[RequestCheck], None]
	auth: Optional[RequestCheck]
	parameters: Optional[RequestCheck]
	qs: Optional[RequestCheck]
	headers: Optional[RequestCheck]
	body: Optional[Callable[[Request], object]]
	response: object
	summary: Optional[str]
	description: Optional[str]
	tags: Union[str, Sequence[str], None]
	on_request: Union[RequestFilter, Sequence[RequestFilter], None]
	on_response: Union[ResponseFilter, Sequence[ResponseFilter], None]


class RequestRunner(ABC):
	"""Configure a handler through class declarations and instantiate it per request."""

	properties: RequestProperties

	def __init_subclass__(
		cls,
		*,
		method: Optional[str] = None,
		url: Optional[str] = None,
		origin: Union[RequestCheck, Sequence[RequestCheck], None] = None,
		auth: Optional[RequestCheck] = None,
		parameters: Optional[RequestCheck] = None,
		qs: Optional[RequestCheck] = None,
		headers: Optional[RequestCheck] = None,
		body: Optional[Callable[[Request], object]] = None,
		response: object = None,
		summary: Optional[str] = None,
		description: Optional[str] = None,
		tags: Union[str, Sequence[str], None] = None,
		onRequest: Union[RequestFilter, Sequence[RequestFilter], None] = None,
		onResponse: Union[ResponseFilter, Sequence[ResponseFilter], None] = None,
	):
		super().__init_subclass__()
		if (method is None) != (url is None):
			raise TypeError('method and url must be specified together')
		if method is not None and fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", method) is None:
			raise ValueError('Invalid HTTP method token')
		if url is not None and (not url.startswith('/') or '?' in url or '#' in url):
			raise ValueError('url must be a path starting with /')
		cls.properties = RequestProperties(
			method=method,
			url=url,
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
			on_request=onRequest,
			on_response=onResponse,
		)
		return

	@abstractmethod
	def run(
		self,
		request: Request,
	) -> Optional[Response]:
		"""Return a Response, or write through request.writer and return None."""
		raise NotImplementedError
