from logging import getLogger
from typing import (
	Optional,
	Sequence,
	Union,
)

from ..Application import Application
from ..Extension import (
	Extension,
	ExtensionCleanup,
	ExtensionRequest,
	ExtensionRequestError,
	ExtensionRequestResponse,
	ExtensionStartup,
)
from ..Request import Request
from ..Response import Response
from ..Responses import ResponseJSON
from .Utils.Routes import (
	http_routes,
	validate_path,
)

__all__ = (
	'Ping',
)


class Ping(Extension):
	"""Report the current running state of the application connected at startup."""

	logger = getLogger('DefChord.Extensions.Ping')

	def __init__(
		self,
		path: str,
		*,
		on_startup: Optional[Union[
			ExtensionStartup,
			Sequence[ExtensionStartup],
		]] = None,
		on_cleanup: Optional[Union[
			ExtensionCleanup,
			Sequence[ExtensionCleanup],
		]] = None,
		on_request: Optional[Union[
			ExtensionRequest,
			Sequence[ExtensionRequest],
		]] = None,
		on_request_response: Optional[Union[
			ExtensionRequestResponse,
			Sequence[ExtensionRequestResponse],
		]] = None,
		on_request_error: Optional[Union[
			ExtensionRequestError,
			Sequence[ExtensionRequestError],
		]] = None,
	):
		super().__init__(
			on_startup=on_startup,
			on_cleanup=on_cleanup,
			on_request=on_request,
			on_request_response=on_request_response,
			on_request_error=on_request_error,
		)
		validate_path(path)
		self.path = path
		return

	def __str__(self) -> str:
		return '{}({})'.format(type(self).__name__, self.path)

	def startup(
		self,
		application: Application,
	) -> None:
		self.application = application
		for route in http_routes(self, self.path):
			application.add_extension_route(self, route)
		super().startup(application)
		return

	def __call__(
		self,
		request: Request,
	) -> Response:
		running = self.application.running
		self.logger.debug('Application state observed: request_id=%s running=%s', request.id, running)
		return ResponseJSON(
			{'status': 'running' if running else 'stopped'},
			status=200 if running else 503,
		)
