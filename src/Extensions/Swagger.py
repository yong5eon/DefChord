from typing import (
	Optional,
	TYPE_CHECKING,
)

from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from .Pages import page
from .Spec import Spec

if TYPE_CHECKING:
	from ..Application import Application


class Swagger(Extension):
	"""동일 Application의 Spec을 CDN 기반 Swagger UI로 제공한다."""

	def __init__(
		self,
		path: str,
		*,
		title: str = 'DefStar',
		description: str = '',
	):
		super().__init__(path)
		if not isinstance(title, str) or not title or not isinstance(description, str):
			raise ValueError('Swagger 제목과 설명은 문자열이어야 합니다')
		self.title = title
		self.description = description
		self.spec: Optional[Spec] = None
		return

	def bind(
		self,
		app: 'Application',
	) -> None:
		specs = [extension for extension in app.exts.values() if isinstance(extension, Spec)]
		if len(specs) != 1:
			raise ValueError('Swagger에는 정확히 하나의 Spec 확장이 필요합니다')
		self.spec = specs[0]
		return

	def handle(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		if self.spec is None:
			raise RuntimeError('Swagger가 Spec에 연결되지 않았습니다')
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
