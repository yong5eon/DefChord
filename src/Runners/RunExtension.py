from typing import TYPE_CHECKING

from ..Extension import Extension
from ..Request import Request
from ..RequestRunner import RequestRunner
from ..Response import Response

if TYPE_CHECKING:
	from ..Application import Application


def extension_handler(
	app: 'Application',
	extension: Extension,
	method: str,
):
	class RunExtension(
		RequestRunner,
		method=method,
		url=extension.path,
	):
		def run(
			self,
			request: Request,
		) -> Response:
			return extension.handle(
				app,
				request,
			)

	return RunExtension
