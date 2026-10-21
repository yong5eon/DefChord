from typing import TYPE_CHECKING

from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from ..Responses import ResponseJSON

if TYPE_CHECKING:
	from ..Application import Application


class HealthCheck(Extension):
	"""HTTP 처리 흐름의 응답 가능 여부와 Application 실행 상태를 제공한다."""

	def handle(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		return ResponseJSON(
			{'status': 'running' if app.running else 'stopped'},
			status=200 if app.running else 503,
		)
