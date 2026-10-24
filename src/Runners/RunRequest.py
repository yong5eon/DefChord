from typing import (
	Optional,
	Type,
)

from ..RequestRunner import RequestRunner
from ..Request import Request
from ..Response import (
	Response,
	close_bodies,
)
from ..CrossOriginResourceSharing import CrossOriginResourceSharing

__all__ = (
	'RunRequest',
)


class RunRequest:
	"""검증·핸들러 실행·응답 후처리와 오류 관찰의 경계를 관리한다."""

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

		def apply_response_hooks(response: Response) -> Response:
			for hook in properties.on_request_response:
				previous = response
				previous_body = previous.body
				try:
					result = hook(request, previous)
					if not isinstance(result, Response):
						raise TypeError('RequestRunnerRequestResponse hooks must return a Response')
				except Exception:
					close_bodies(
						previous_body,
						previous.body,
						preserve_error=True,
					)
					raise
				response = result
				try:
					close_bodies(*(
						body for body in (
							previous_body,
							previous.body,
						)
						if body is not response.body
					))
				except Exception:
					close_bodies(
						response.body,
						preserve_error=True,
					)
					raise
			try:
				return self.cross_origin_resource_sharing.apply_to_response(
					request,
					response,
				)
			except Exception:
				close_bodies(
					response.body,
					preserve_error=True,
				)
				raise

		writer = None
		try:
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
			for hook in properties.on_request:
				result = hook(request)
				if not isinstance(result, Request):
					raise TypeError('RequestRunnerRequest hooks must return a Request')
				request = result
			writer = request.response_writer
			if writer is not None:
				writer.on_request_response = apply_response_hooks
			response = runner.run(request)
			if writer is not None and writer.started:
				if response is not None:
					if isinstance(response, Response):
						close_bodies(
							response.body,
							preserve_error=True,
						)
					raise RuntimeError('Cannot return a Response after starting direct output')
				writer.end()
				return None
			if not isinstance(response, Response):
				raise TypeError('run must return a Response or start a response through the writer')
			return apply_response_hooks(response)
		except Exception as error:
			for hook in properties.on_request_error:
				if hook(request, error) is not None:
					raise TypeError('RequestRunnerRequestError hooks must return None')
			raise
		finally:
			if writer is not None:
				writer.on_request_response = None
