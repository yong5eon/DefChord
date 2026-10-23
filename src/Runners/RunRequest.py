from typing import (
	Optional,
	Sequence,
	Type,
	TypeVar,
	Union,
)

from ..RequestRunner import RequestRunner
from ..Request import Request
from ..Response import Response
from ..CrossOriginResourceSharing import CrossOriginResourceSharing

__all__ = (
	'RunRequest',
)


T = TypeVar('T')


def filters(
	value: Union[T, Sequence[T], None],
) -> Sequence[T]:
	if value is None:
		return ()
	if isinstance(value, Sequence):
		return value
	return (value,)


class RunRequest:
	"""Execute handlers while preserving validation, body, and filter ordering."""

	def __init__(
		self,
		obj: Type[RequestRunner],
	):
		self.object = obj
		self.cross_origin_resource_sharing = CrossOriginResourceSharing(obj.properties)
		return

	def run(
		self,
		request: Request,
	) -> Optional[Response]:
		properties = self.object.properties
		self.cross_origin_resource_sharing.validate_origin(request)
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
					raise TypeError('Request filters must return a Response or None')
				return self.cross_origin_resource_sharing.apply_to_response(
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
						raise TypeError('Response filters must return a Response')
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
				return self.cross_origin_resource_sharing.apply_to_response(
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
				raise RuntimeError('Cannot return a Response after starting direct output')
			writer.end()
			return None
		if not isinstance(response, Response):
			raise TypeError('run must return a Response or start a response through the writer')
		return apply_response_filters(response)
