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
from .Utils import page
from .Utils.Routes import (
	http_routes,
	validate_path,
)

__all__ = (
	'Status',
)


class Status(Extension):
	"""명시적인 같은 출처 Metrics 경로를 사용하는 상태 페이지."""

	def __init__(
		self,
		path: str,
		*,
		metrics_uri: str,
		title: str = 'DefEssential',
		description: str = '',
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
		if (
			not isinstance(metrics_uri, str)
			or not metrics_uri.startswith('/')
			or metrics_uri.startswith('//')
			or any(character.isspace() or ord(character) < 32 or character == '\\' for character in metrics_uri)
		):
			raise ValueError('Status metrics_uri must be a same-origin absolute path')
		if not isinstance(title, str) or not title or not isinstance(description, str):
			raise ValueError('Status title must be a non-empty string and description must be a string')
		self.title = title
		self.description = description
		self.metrics_uri = metrics_uri
		return

	def __str__(self) -> str:
		return '{}(uri={}, metrics={})'.format(type(self).__name__, self.path, self.metrics_uri)

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
	) -> Response:
		return page(
			'Status',
			self.title,
			self.description,
			parameters={'metrics_uri': self.metrics_uri},
		)
