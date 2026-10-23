from typing import (
	Optional,
	Type,
)
from urllib.parse import unquote

from .RequestRunner import RequestRunner
from .Route import Route

__all__ = (
	'FileSystemRoute',
)


class FileSystemRoute(Route):
	"""Map file paths, including path separators, under a URL prefix."""

	def __init__(
		self,
		prefix: str,
		obj: Type[RequestRunner],
		*,
		method: str = 'GET',
	):
		super().__init__(
			method,
			prefix,
			obj,
		)
		self.prefix = prefix.rstrip('/') + '/'
		return

	@property
	def priority(self) -> tuple[int, int, int]:
		return (
			1,
			0,
			-len(self.prefix),
		)

	def match(
		self,
		url: str,
	) -> Optional[dict[str, str]]:
		if url.startswith(self.prefix):
			return {'path': unquote(url[len(self.prefix):])}
		return None
