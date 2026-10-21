from typing import (
	Optional,
	Type,
)
from urllib.parse import unquote

from ..Request import Request
from ..RequestRunner import RequestRunner
from ..Response import Response
from ..Responses import ResponseFile
from ..Responses.ResponseFile import file_error
from ..Route import Route
from ..Utils.FileSystemObject import Connection


class FileSystemRoute(Route):
	"""Map file paths, including path separators, under a URL prefix."""

	def __init__(
		self,
		prefix: str,
		obj: Type[RequestRunner],
	):
		super().__init__(
			'GET',
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


def filesystem_handler(
	fso: Connection,
	prefix: str,
	on_request=None,
	on_response=None,
) -> FileSystemRoute:
	class RunFileSystemObject(
		RequestRunner,
		method='GET',
		url=prefix,
		onRequest=on_request,
		onResponse=on_response,
	):
		def run(
			self,
			request: Request,
		) -> Response:
			path = request.parameters['path']
			try:
				format, encoding = fso.type(path)
				file = fso.open(
					path,
					mode='rb',
				)
			except (
				FileNotFoundError,
				NotADirectoryError,
				IsADirectoryError,
				PermissionError,
			) as error:
				raise file_error(error) from error
			return ResponseFile(
				file,
				format=format,
				encoding=encoding,
			)

	return FileSystemRoute(
		prefix,
		RunFileSystemObject,
	)
