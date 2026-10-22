from typing import Type

from ..Request import Request
from ..RequestRunner import RequestRunner
from ..Responses import ResponseFile
from .RunFactory import RunFactory


class RunFileFactory(RunFactory[Type[RequestRunner]]):
	"""고정 URL에서 파일을 반환하는 요청 처리 클래스를 생성한다."""

	def __init__(
		self,
		path,
		url: str,
		on_request=None,
		on_response=None,
	):
		self.path = path
		self.url = url
		self.on_request = on_request
		self.on_response = on_response
		return

	def __call__(self) -> Type[RequestRunner]:
		path = self.path

		class RunFile(
			RequestRunner,
			method='GET',
			url=self.url,
			onRequest=self.on_request,
			onResponse=self.on_response,
		):
			def run(
				self,
				request: Request,
			) -> ResponseFile:
				return ResponseFile(path)

		return RunFile
