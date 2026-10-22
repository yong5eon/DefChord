from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from ..Responses import ResponseJSON


class Ping(Extension):
	"""HTTP 응답 여부와 Application 실행 상태를 제공한다."""

	def __call__(
		self,
		app: Application,
		request: Request,
	) -> Response:
		return ResponseJSON(
			{'status': 'running' if app.running else 'stopped'},
			status=200 if app.running else 503,
		)
