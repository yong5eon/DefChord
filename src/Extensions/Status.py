from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..Response import Response
from .Utils import page

__all__ = (
	'Status',
)


class Status(Extension):
	"""Display JSON metrics from an explicit same-origin path."""

	def __init__(
		self,
		path: str,
		*,
		metrics_uri: str,
		title: str = 'DefEssential',
		description: str = '',
	):
		super().__init__(path)
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

	def __call__(
		self,
		app: Application,
		request: Request,
	) -> Response:
		return page(
			'Status',
			self.title,
			self.description,
			parameters={'metrics_uri': self.metrics_uri},
		)
