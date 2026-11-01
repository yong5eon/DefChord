from logging import getLogger
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
	"""Manage validation, handler execution, response processing, and error observation."""

	logger = getLogger('DefChord.RequestRunner')

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
		request_id = request.id
		phase = 'runner.cors_origin'

		def apply_response_hooks(response: Response) -> Response:
			for index, hook in enumerate(properties.on_request_response):
				previous = response
				previous_body = previous.body
				phase = 'runner.response_hook.' + str(index)
				self.logger.debug(
					'Response hook starting: request_id=%s phase=%s hook=%s',
					request.id,
					phase,
					type(hook).__qualname__,
				)
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
				self.logger.debug('Response hook completed: request_id=%s phase=%s', request.id, phase)
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
				self.logger.debug('CORS response starting: request_id=%s', request.id)
				response = self.cross_origin_resource_sharing.apply_to_response(
					request,
					response,
				)
				self.logger.debug('CORS response completed: request_id=%s', request.id)
				return response
			except Exception:
				close_bodies(
					response.body,
					preserve_error=True,
				)
				raise

		writer = None
		try:
			self.logger.debug('CORS origin check starting: request_id=%s', request.id)
			self.cross_origin_resource_sharing.validate_origin(request)
			self.logger.debug('CORS origin check completed: request_id=%s', request.id)
			for name, check in (
				(
					'auth',
					properties.auth,
				),
				(
					'parameters',
					properties.parameters,
				),
				(
					'query',
					properties.qs,
				),
				(
					'headers',
					properties.headers,
				),
			):
				if check is not None:
					phase = 'runner.validation.' + name
					self.logger.debug(
						'Validation starting: request_id=%s phase=%s validator=%s',
						request.id,
						phase,
						type(check).__qualname__,
					)
					check(request)
					self.logger.debug('Validation completed: request_id=%s phase=%s', request.id, phase)
			if properties.body is not None:
				phase = 'runner.body'
				self.logger.debug('Request body processing: request_id=%s processor=%s', request.id, type(properties.body).__qualname__)
				request.body = properties.body(request)
				self.logger.debug('Request body processed: request_id=%s', request.id)
			phase = 'runner.create'
			self.logger.debug('Handler creating: request_id=%s handler=%s.%s', request.id, self.object.__module__, self.object.__qualname__)
			runner = self.object()
			self.logger.debug('Handler created: request_id=%s', request.id)
			for index, hook in enumerate(properties.on_request):
				phase = 'runner.request_hook.' + str(index)
				self.logger.debug('Request hook starting: request_id=%s phase=%s hook=%s', request.id, phase, type(hook).__qualname__)
				result = hook(request)
				if not isinstance(result, Request):
					raise TypeError('RequestRunnerRequest hooks must return a Request')
				self.logger.debug('Request hook completed: request_id=%s phase=%s', request.id, phase)
				if request.id != result.id:
					self.logger.debug('Request replaced: previous_request_id=%s request_id=%s', request.id, result.id)
				request = result
			writer = request.response_writer
			if writer is not None:
				writer.on_request_response = apply_response_hooks
			phase = 'runner.run'
			self.logger.debug('Handler running: request_id=%s handler=%s.%s', request.id, self.object.__module__, self.object.__qualname__)
			response = runner.run(request)
			self.logger.debug('Handler returned: request_id=%s', request.id)
			phase = 'runner.response_validation'
			if writer is not None and writer.started:
				if response is not None:
					if isinstance(response, Response):
						close_bodies(
							response.body,
							preserve_error=True,
						)
					raise RuntimeError('Cannot return a Response after starting direct output')
				phase = 'runner.direct_end'
				self.logger.debug('Direct response ending: request_id=%s', request.id)
				writer.end()
				self.logger.debug('Runner response provided: request_id=%s mode=direct', request.id)
				return None
			if not isinstance(response, Response):
				raise TypeError('run must return a Response or start a response through the writer')
			phase = 'runner.response_hooks'
			response = apply_response_hooks(response)
			self.logger.debug(
				'Runner response provided: request_id=%s mode=returned status=%s',
				request.id,
				response.status,
			)
			return response
		except Exception as error:
			self.logger.debug(
				'Runner failed: request_id=%s phase=%s handler=%s error_type=%s',
				request_id,
				phase,
				self.object.__module__ + '.' + self.object.__qualname__,
				type(error).__qualname__,
			)
			for index, hook in enumerate(properties.on_request_error):
				self.logger.debug(
					'Error hook starting: request_id=%s phase=runner.error_hook.%s hook=%s',
					request.id,
					index,
					type(hook).__qualname__,
				)
				response = hook(request, error)
				if response is not None and not isinstance(response, Response):
					raise TypeError('RequestRunnerRequestError hooks must return a Response or None')
				if response is not None:
					active_writer = request.response_writer
					if active_writer is not None and active_writer.started:
						close_bodies(
							response.body,
							preserve_error=True,
						)
						raise RuntimeError('Cannot return a Response after starting direct output')
					return response
				self.logger.debug('Error hook completed: request_id=%s index=%s', request.id, index)
			raise
		finally:
			if writer is not None:
				writer.on_request_response = None
