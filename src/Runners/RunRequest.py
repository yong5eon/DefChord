from typing import (
	Callable,
	Optional,
	Sequence,
	Type,
	TypeVar,
	Union,
)

from ..RequestRunner import RequestRunner
from ..Request import Request
from ..Response import Response
from ..CORS import (
	apply_cors,
	check_origin,
)
from ..Validators import Origin


T = TypeVar('T')


def filters(
	value: Union[Callable[..., T], Sequence[Callable[..., T]], None],
) -> Sequence[Callable[..., T]]:
	if value is None:
		return ()
	if callable(value):
		return (value,)
	return value


class RunRequest:
	"""기존 검증·본문·필터 적용 순서를 유지하는 실행 처리."""

	def __init__(
		self,
		obj: Type[RequestRunner],
	):
		self.object = obj
		return

	def run(
		self,
		request: Request,
	) -> Optional[Response]:
		properties = self.object.properties
		check_origin(
			properties,
			request,
		)
		for origin in filters(properties.origin):
			if not isinstance(origin, Origin):
				origin(request)
		for check in (
			properties.auth,
			properties.parameters,
			properties.qs,
			properties.headers,
		):
			if check is not None:
				check(request)
		if properties.body is not None:
			request.body = properties.body(request)
		runner = self.object()
		for on_request in filters(properties.on_request):
			request, response = on_request(request)
			if response is not None:
				if not isinstance(response, Response):
					raise TypeError('요청 필터는 Response 또는 None을 반환해야 합니다')
				return apply_cors(
					properties,
					request,
					response,
				)
		def apply_response_filters(response: Response) -> Response:
			for on_response in filters(properties.on_response):
				previous = response
				previous_body = previous.body
				try:
					response = on_response(
						request,
						previous,
					)
					if not isinstance(response, Response):
						raise TypeError('응답 필터는 Response를 반환해야 합니다')
				except Exception:
					previous.close()
					raise
				finally:
					if previous.body is not previous_body:
						close = getattr(previous_body, 'close', None)
						if close is not None:
							close()
				if response is not previous and response.body is not previous_body:
					previous.close()
			try:
				return apply_cors(
					properties,
					request,
					response,
				)
			except Exception:
				response.close()
				raise

		writer = request.response_writer
		if writer is not None:
			writer.on_response = apply_response_filters
		response = runner.run(request)
		if writer is not None and writer.started:
			if response is not None:
				if isinstance(response, Response):
					response.close()
				raise RuntimeError('직접 출력 후 Response를 반환할 수 없습니다')
			writer.end()
			return None
		if not isinstance(response, Response):
			raise TypeError('run은 Response를 반환하거나 Writer로 응답을 시작해야 합니다')
		return apply_response_filters(response)
