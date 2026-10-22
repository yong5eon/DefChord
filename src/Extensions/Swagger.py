from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from .Pages import page


class Swagger(Extension):
	"""Serve CDN-hosted Swagger UI for an explicit same-origin specification path."""

	def __init__(
		self,
		path: str,
		*,
		spec_uri: str,
		title: str = 'DefEssential',
		description: str = '',
	):
		super().__init__(path)
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

	def __call__(
		self,
		app: Application,
		request: Request,
	) -> Response:
		return page(
			'Swagger',
			self.title,
			self.description,
			parameters={'spec_url': self.spec_uri},
			policy=(
				"default-src 'none'; "
				"script-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/; "
				"style-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/; "
				"img-src 'self' data:; font-src 'self' data:; "
				"connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
			),
		)
