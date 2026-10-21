from typing import Type

from ..Request import Request
from ..RequestRunner import RequestRunner
from ..Responses import ResponseFile


def file_handler(
	path,
	url: str,
	on_request=None,
	on_response=None,
) -> Type[RequestRunner]:
	class RunFile(
		RequestRunner,
		method='GET',
		url=url,
		onRequest=on_request,
		onResponse=on_response,
	):
		def run(
			self,
			request: Request,
		) -> ResponseFile:
			return ResponseFile(path)

	return RunFile
