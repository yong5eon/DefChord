from pathlib import Path
from typing import (
	Sequence,
	Union,
)

from ..Application import Application
from ..Extension import Extension
from ..Request import Request
from ..RequestRunner import (
	RequestFilter,
	ResponseFilter,
)
from ..Responses import ResponseFile

__all__ = (
	'File',
)


class File(Extension):
	"""Serve a file at a fixed HTTP path."""

	def __init__(
		self,
		path: str,
		file: Union[str, Path],
		*,
		onRequest: Union[RequestFilter, Sequence[RequestFilter], None] = None,
		onResponse: Union[ResponseFilter, Sequence[ResponseFilter], None] = None,
	):
		super().__init__(
			path,
			onRequest=onRequest,
			onResponse=onResponse,
		)
		self.file = Path(file).resolve()
		return

	def __call__(
		self,
		app: Application,
		request: Request,
	) -> ResponseFile:
		return ResponseFile(self.file)
