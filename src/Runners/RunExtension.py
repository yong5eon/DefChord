from typing import (
	TYPE_CHECKING,
	Type,
)

from ..Extension import Extension
from ..Request import Request
from ..RequestRunner import RequestRunner
from ..Response import Response
from .RunFactory import RunFactory

if TYPE_CHECKING:
	from ..Application import Application


class RunExtensionFactory(RunFactory[Type[RequestRunner]]):
	"""확장 호출을 위임하는 요청 처리 클래스를 생성한다."""

	def __init__(
		self,
		app: 'Application',
		extension: Extension,
		method: str,
	):
		self.app = app
		self.extension = extension
		self.method = method
		return

	def __call__(self) -> Type[RequestRunner]:
		app = self.app
		extension = self.extension

		class RunExtension(
			RequestRunner,
			method=self.method,
			url=extension.path,
			name=type(extension).__name__,
			onRequest=extension.on_request,
			onResponse=extension.on_response,
		):
			def run(
				self,
				request: Request,
			) -> Response:
				return extension(
					app,
					request,
				)

		return RunExtension
