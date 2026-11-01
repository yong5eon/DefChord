from pathlib import Path
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
from ..Responses import ResponseFile
from .Utils.Routes import (
	http_routes,
	validate_path,
)

__all__ = (
	'File',
)


class File(Extension):
	"""Serve a file at a fixed HTTP path with per-instance user hooks."""

	logger = getLogger('DefChord.Extensions.File')

	def __init__(
		self,
		path: str,
		file: Union[
			str,
			Path,
		],
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
		self.file = Path(file).resolve()
		return

	def __str__(self) -> str:
		return '{}(uri={}, path={})'.format(type(self).__name__, self.path, self.file)

	def startup(
		self,
		application: Application,
	) -> None:
		for route in http_routes(self, self.path):
			application.add_extension_route(self, route)
		super().startup(application)
		return

	def __call__(
		self,
		request: Request,
	) -> ResponseFile:
		self.logger.debug('File response preparing: request_id=%s', request.id)
		response = ResponseFile(self.file)
		self.logger.debug('File response prepared: request_id=%s', request.id)
		return response
