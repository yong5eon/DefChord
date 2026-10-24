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
from .Utils import page
from .Utils.Routes import (
	http_routes,
	validate_path,
)

__all__ = (
	'Swagger',
)


class Swagger(Extension):
	"""Connect Swagger UI to an explicitly configured same-origin specification path."""

	logger = getLogger('DefEssential.Extensions.Swagger')

	def __init__(
		self,
		path: str,
		*,
		spec_uri: str,
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
			not isinstance(spec_uri, str)
			or not spec_uri.startswith('/')
			or spec_uri.startswith('//')
			or any(character.isspace() or ord(character) < 32 or character == '\\' for character in spec_uri)
		):
			raise ValueError('Swagger spec_uri must be a same-origin absolute path')
		if not isinstance(title, str) or not title or not isinstance(description, str):
			raise ValueError('Swagger title must be a non-empty string and description must be a string')
		self.title = title
		self.description = description
		self.spec_uri = spec_uri
		return

	def __str__(self) -> str:
		return '{}(uri={}, spec={})'.format(type(self).__name__, self.path, self.spec_uri)

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
		self.logger.debug('Swagger page preparing: request_id=%s', request.id)
		response = page(
			'Swagger',
			self.title,
			self.description,
			parameters={'spec_url': self.spec_uri},
			policy=(
				"default-src 'none'; "
				"script-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/; "
				"style-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/; "
				"img-src 'self' data: blob:; font-src 'self' data:; "
				"connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
			),
		)
		self.logger.debug('Swagger page prepared: request_id=%s', request.id)
		return response
