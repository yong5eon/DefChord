from typing import (
	Optional,
	TYPE_CHECKING,
)

from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from ..Responses import ResponseJSON
from .Metrics import Metrics
from .Pages import page

if TYPE_CHECKING:
	from ..Application import Application


class Dashboard(Extension):
	"""Metrics 스냅샷을 HTML과 JSON으로 표시한다."""

	def __init__(
		self,
		path: str,
		*,
		title: str = 'DefStar',
		description: str = '',
	):
		super().__init__(path)
		if not isinstance(title, str) or not title or not isinstance(description, str):
			raise ValueError('Dashboard 제목과 설명은 문자열이어야 합니다')
		self.title = title
		self.description = description
		self.metrics: Optional[Metrics] = None
		return

	def bind(
		self,
		app: 'Application',
	) -> None:
		metrics = [extension for extension in app.exts.values() if isinstance(extension, Metrics)]
		if len(metrics) != 1:
			raise ValueError('Dashboard에는 정확히 하나의 Metrics 확장이 필요합니다')
		self.metrics = metrics[0]
		return

	def handle(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		if request.header('Accept') == 'application/json':
			if self.metrics is None:
				raise RuntimeError('Dashboard가 Metrics에 연결되지 않았습니다')
			return ResponseJSON(
				self.metrics.snapshot(app),
				headers={'Cache-Control': 'no-store'},
			)
		return page(
			'Dashboard',
			self.title,
			self.description,
		)
