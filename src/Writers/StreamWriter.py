from typing import (
	Mapping,
	Optional,
)

from ..Response import Response
from ..ResponseWriter import ResponseWriter


class StreamWriter:
	"""Start a response and write bytes directly to the stream."""

	chunked = False

	def __init__(
		self,
		writer: ResponseWriter,
	):
		self.writer = writer
		return

	def begin(
		self,
		headers: Optional[Mapping[str, str]] = None,
		format: Optional[str] = None,
		charset: Optional[str] = None,
		status: int = 200,
	) -> None:
		self.writer.begin(
			Response(
				status=status,
				headers=headers,
				format=format,
				charset=charset,
			),
			chunked=self.chunked,
		)
		return

	def write(
		self,
		data: bytes,
	) -> None:
		self.writer.write(data)
		return

	def flush(self) -> None:
		self.writer.flush()
		return

	def end(self) -> None:
		self.writer.end()
		return
