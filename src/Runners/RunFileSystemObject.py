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
from ..Utils.FileSystemObject.Implements.FileSystem.Connection import Connection as LocalConnection
from .RunFactory import RunFactory


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


class RunFileSystemObjectFactory(RunFactory[FileSystemRoute]):
	"""파일시스템 연결을 사용하는 접두사 경로와 처리 클래스를 생성한다."""

	def __init__(
		self,
		fso: Connection,
		prefix: str,
		on_request=None,
		on_response=None,
	):
		self.fso = fso
		self.prefix = prefix
		self.on_request = on_request
		self.on_response = on_response
		return

	def __call__(self) -> FileSystemRoute:
		fso = self.fso
		name = (
			f'RunFileSystemObject({fso.base})'
			if isinstance(fso, LocalConnection)
			else f'RunFileSystemObject({self.prefix})'
		)

		class RunFileSystemObject(
			RequestRunner,
			method='GET',
			url=self.prefix,
			name=name,
			onRequest=self.on_request,
			onResponse=self.on_response,
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
			self.prefix,
			RunFileSystemObject,
		)
