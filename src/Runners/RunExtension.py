from typing import (
	Optional,
	Type,
)

from ..Extension import Extension
from ..Request import Request
from ..RequestRunner import RequestRunner
from ..Response import Response
from .RunFactory import RunFactory

__all__ = (
	'RunExtensionFactory',
)

def run_extension(
	extension: Extension,
	request: Request,
) -> Optional[Response]:
	"""내부 RequestRunner 검증 이후의 확장 처리 경계만 감싼다."""
	try:
		for hook in extension.request_hooks:
			result = hook(request)
			if not isinstance(result, Request):
				raise TypeError('ExtensionRequest hooks must return a Request')
			request = result
		response = extension(request)
		if response is not None and not isinstance(response, Response):
			raise TypeError('Extension must return a Response or None')
		writer = request.response_writer
		if response is None and (writer is None or not writer.started):
			raise TypeError('Extension must return a Response or start direct output')
		if response is not None and writer is not None and writer.started:
			response.close()
			raise RuntimeError('Cannot return a Response after starting direct output')
		for hook in extension.request_response_hooks:
			previous = response
			previous_body = previous.body if previous is not None else None
			try:
				response = hook(request, response)
				if response is not None and not isinstance(response, Response):
					raise TypeError('ExtensionRequestResponse hooks must return a Response or None')
				if previous is None and response is not None:
					response.close()
					raise TypeError('ExtensionRequestResponse hooks cannot replace direct output')
				writer = request.response_writer
				if response is None and (writer is None or not writer.started):
					raise TypeError('ExtensionRequestResponse hooks cannot discard a response without direct output')
			except Exception:
				if previous is not None:
					previous.close()
				raise
			finally:
				if previous is not None and previous.body is not previous_body:
					close = getattr(previous_body, 'close', None)
					if close is not None:
						close()
			if previous is not None and response is not previous:
				if response is None or response.body is not previous_body:
					previous.close()
		return response
	except Exception as error:
		for hook in extension.request_error_hooks:
			if hook(request, error) is not None:
				raise TypeError('ExtensionRequestError hooks must return None')
		raise


class RunExtensionFactory(RunFactory[Type[RequestRunner]]):
	"""확장 호출을 위임하는 요청 처리 클래스를 생성한다."""

	def __init__(
		self,
		extension: Extension,
		method: str,
		path: str,
	):
		self.extension = extension
		self.method = method
		self.path = path
		return

	def __call__(self) -> Type[RequestRunner]:
		extension = self.extension

		class RunExtension(
			RequestRunner,
			method=self.method,
			url=self.path,
			name=type(extension).__name__,
		):
			def run(
				self,
				request: Request,
			) -> Optional[Response]:
				return run_extension(
					extension,
					request,
				)

		return RunExtension
