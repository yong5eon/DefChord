from typing import (
	Sequence,
	Type,
	Union,
)

from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..RequestRunner import (
	RequestRunner,
	RequestFilter,
	ResponseFilter,
)
from ..Responses import ResponseFile
from ..Responses.ResponseFile import file_error
from ..FileSystemRoute import FileSystemRoute
from ..Utils.FileSystemObject import Connection


class FileSystem(Extension):
	"""Serve files from a connection under an HTTP path prefix."""

	def __init__(
		self,
		path: str,
		connection: Connection,
		*,
		onRequest: Union[RequestFilter, Sequence[RequestFilter], None] = None,
		onResponse: Union[ResponseFilter, Sequence[ResponseFilter], None] = None,
	):
		super().__init__(
			path,
			onRequest=onRequest,
			onResponse=onResponse,
		)
		self.connection = connection
		return

	def route(
		self,
		method: str,
		handler: Type[RequestRunner],
	) -> FileSystemRoute:
		return FileSystemRoute(
			self.path,
			handler,
			method=method,
		)

	def start(self, app: Application) -> None:
		self.connection.connect()
		return

	def stop(self, app: Application) -> None:
		self.connection.close()
		return

	def __call__(
		self,
		app: Application,
		request: Request,
	) -> ResponseFile:
		path = request.parameters['path']
		try:
			format, encoding = self.connection.type(path)
			file = self.connection.open(
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
