from logging import getLogger
from typing import (
	Optional,
	Sequence,
	Type,
	Union,
)
from urllib.parse import unquote

from ..Application import Application
from ..Extension import (
	Extension,
	ExtensionCleanup,
	ExtensionRequest,
	ExtensionRequestError,
	ExtensionRequestResponse,
	ExtensionStartup,
)
from ..Request import Request
from ..RequestRunner import RequestRunner
from ..Route import Route
from ..Runners.RunExtension import RunExtensionFactory
from ..Responses import ResponseFile
from ..Responses.ResponseFile import file_error
from ..Utils.FileSystemObject import Connection
from .Utils.Routes import (
	validate_path,
)

__all__ = (
	'FileSystem',
	'FileSystemRoute',
)


class FileSystemRoute(Route):
	"""URL 접두사 아래의 하위 파일 경로를 매칭한다."""

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


class FileSystem(Extension):
	"""주입된 연결에서 요청 파일을 응답한다."""

	def __init__(
		self,
		path: str,
		connection: Connection,
		*,
		on_startup: Optional[Union[
			ExtensionStartup,
			Sequence[ExtensionStartup],
		]] = None,
		on_cleanup: Optional[Union[
			ExtensionCleanup,
			Sequence[ExtensionCleanup],
		]] = None,
		on_request: Optional[Union[
			ExtensionRequest,
			Sequence[ExtensionRequest],
		]] = None,
		on_request_response: Optional[Union[
			ExtensionRequestResponse,
			Sequence[ExtensionRequestResponse],
		]] = None,
		on_request_error: Optional[Union[
			ExtensionRequestError,
			Sequence[ExtensionRequestError],
		]] = None,
	):
		super().__init__(
			on_startup=on_startup,
			on_cleanup=on_cleanup,
			on_request=on_request,
			on_request_response=on_request_response,
			on_request_error=on_request_error,
		)
		validate_path(path)
		self.path = path
		self.connection = connection
		return

	def __str__(self) -> str:
		return '{}(uri={}, path={})'.format(type(self).__name__, self.path, self.connection.base)  # type: ignore

	def startup(
		self,
		application: Application,
	) -> None:
		try:
			for method in (
				'GET',
				'HEAD',
			):
				application.add_extension_route(
					self,
					FileSystemRoute(
						self.path,
						RunExtensionFactory(
							self,
							method,
							self.path,
						)(),
						method=method,
					),
				)
			self.connection.connect()
			super().startup(application)
		except Exception:
			try:
				self.connection.close()
			except Exception:
				getLogger('DefEssential.Extensions.FileSystem').exception('시작 실패 후 연결 정리에 실패했습니다')
			raise
		return

	def cleanup(self) -> None:
		error = None
		try:
			super().cleanup()
		except Exception as caught:
			error = caught
		try:
			self.connection.close()
		except Exception:
			if error is None:
				raise
			getLogger('DefEssential.Extensions.FileSystem').exception('사용자 훅 실패 후 연결 정리에 실패했습니다')
		if error is not None:
			raise error
		return

	def __call__(
		self,
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
