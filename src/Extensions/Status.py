from typing import Optional

from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from ..Responses import ResponseJSON
from .Metrics import Metrics
from .Pages import page


class Status(Extension):
	"""Metrics 스냅샷을 HTML과 JSON으로 제공한다."""

	def __init__(
		self,
		path: str,
		*,
		title: str = 'DefEssential',
		description: str = '',
	):
		super().__init__(path)
		if not isinstance(title, str) or not title or not isinstance(description, str):
			raise ValueError('Status title must be a non-empty string and description must be a string')
		self.title = title
		self.description = description
		self.metrics: Optional[Metrics] = None
		return

	def bind(
		self,
		app: Application,
	) -> None:
		metrics = [extension for extension in app.exts.values() if isinstance(extension, Metrics)]
		if len(metrics) != 1:
			raise ValueError('Status requires exactly one Metrics extension')
		self.metrics = metrics[0]
		return

	def handle(
		self,
		app: Application,
		request: Request,
	) -> Response:
		if request.header('Accept') == 'application/json':
			if self.metrics is None:
				raise RuntimeError('Status is not bound to a Metrics extension')
			return ResponseJSON(
				self.metrics.snapshot(app),
				headers={'Cache-Control': 'no-store'},
			)
		return page(
			'Status',
			self.title,
			self.description,
		)
