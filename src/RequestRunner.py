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
	"""클래스 정의에 보관하며 Application 등록 시 사용하는 처리기 설정."""

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
	"""클래스 선언으로 설정하며 요청마다 생성하는 처리기."""

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
			raise TypeError('method와 url을 함께 지정해야 합니다')
		if method is not None and fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", method) is None:
			raise ValueError('잘못된 HTTP 메서드 토큰')
		if url is not None and (not url.startswith('/') or '?' in url or '#' in url):
			raise ValueError('url에는 /로 시작하는 경로를 지정해야 합니다')
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
		"""응답을 반환하거나 request.writer로 직접 전송한 뒤 None을 반환한다."""
		raise NotImplementedError
