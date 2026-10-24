from logging import getLogger
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

logger = getLogger('DefEssential.Extension')


def run_extension(
	extension: Extension,
	request: Request,
) -> Optional[Response]:
	"""Wrap only the extension-processing boundary after internal RequestRunner validation."""
	try:
		for index, hook in enumerate(extension.request_hooks):
			logger.debug('Extension request hook starting: request_id=%s index=%s hook=%s', request.id, index, type(hook).__qualname__)
			result = hook(request)
			if not isinstance(result, Request):
				raise TypeError('ExtensionRequest hooks must return a Request')
			logger.debug('Extension request hook completed: request_id=%s index=%s', request.id, index)
			if request.id != result.id:
				logger.debug('Request replaced: previous_request_id=%s request_id=%s', request.id, result.id)
			request = result
		logger.debug('Extension running: request_id=%s extension=%s', request.id, type(extension).__qualname__)
		response = extension(request)
		if response is not None and not isinstance(response, Response):
			raise TypeError('Extension must return a Response or None')
		writer = request.response_writer
		if response is None and (writer is None or not writer.started):
			raise TypeError('Extension must return a Response or start direct output')
		if response is not None and writer is not None and writer.started:
			response.close()
			raise RuntimeError('Cannot return a Response after starting direct output')
		logger.debug('Extension response provided: request_id=%s extension=%s', request.id, type(extension).__qualname__)
		for index, hook in enumerate(extension.request_response_hooks):
			previous = response
			previous_body = previous.body if previous is not None else None
			try:
				logger.debug('Extension response hook starting: request_id=%s index=%s hook=%s', request.id, index, type(hook).__qualname__)
				response = hook(request, response)
				if response is not None and not isinstance(response, Response):
					raise TypeError('ExtensionRequestResponse hooks must return a Response or None')
				if previous is None and response is not None:
					response.close()
					raise TypeError('ExtensionRequestResponse hooks cannot replace direct output')
				writer = request.response_writer
				if response is None and (writer is None or not writer.started):
					raise TypeError('ExtensionRequestResponse hooks cannot discard a response without direct output')
				logger.debug('Extension response hook completed: request_id=%s index=%s', request.id, index)
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
		logger.debug('Extension failed: request_id=%s extension=%s error_type=%s', request.id, type(extension).__qualname__, type(error).__qualname__)
		for index, hook in enumerate(extension.request_error_hooks):
			logger.debug('Extension error hook starting: request_id=%s index=%s hook=%s', request.id, index, type(hook).__qualname__)
			if hook(request, error) is not None:
				raise TypeError('ExtensionRequestError hooks must return None')
			logger.debug('Extension error hook completed: request_id=%s index=%s', request.id, index)
		raise


class RunExtensionFactory(RunFactory[Type[RequestRunner]]):
	"""Create a request handler class that delegates calls to an extension."""

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
