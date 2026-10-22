from typing import Optional

from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from .Pages import page
from .Spec import Spec


class Swagger(Extension):
	"""Serve the same Application's Spec through CDN-hosted Swagger UI."""

	def __init__(
		self,
		path: str,
		*,
		title: str = 'DefEssential',
		description: str = '',
	):
		super().__init__(path)
		if not isinstance(title, str) or not title or not isinstance(description, str):
			raise ValueError('Swagger title must be a non-empty string and description must be a string')
		self.title = title
		self.description = description
		self.spec: Optional[Spec] = None
		return

	def bind(
		self,
		app: Application,
	) -> None:
		specs = [extension for extension in app.exts.values() if isinstance(extension, Spec)]
		if len(specs) != 1:
			raise ValueError('Swagger requires exactly one Spec extension')
		self.spec = specs[0]
		return

	def __call__(
		self,
		app: Application,
		request: Request,
	) -> Response:
		if self.spec is None:
			raise RuntimeError('Swagger is not bound to a Spec extension')
		return page(
			'Swagger',
			self.title,
			self.description,
			parameters={'spec_url': self.spec.path},
			policy=(
				"default-src 'none'; "
				"script-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/; "
				"style-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/; "
				"img-src 'self' data:; font-src 'self' data:; "
				"connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
			),
		)
