from typing import TYPE_CHECKING

from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from ..Responses import ResponseJSON

if TYPE_CHECKING:
	from ..Application import Application


class HealthCheck(Extension):
	"""Report HTTP responsiveness and Application running state."""

	def handle(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		return ResponseJSON(
			{'status': 'running' if app.running else 'stopped'},
			status=200 if app.running else 503,
		)
