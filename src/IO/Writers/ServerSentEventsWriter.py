from typing import (
	Mapping,
	Optional,
	Union,
)

from ..ResponseWriter import ResponseWriter
from .ServerSentEvents import ServerSentEvents
from .StreamWriter import StreamWriter

__all__ = (
	'ServerSentEventsWriter',
)


def _encode_sse_comment(
	text: str,
) -> bytes:
	lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
	return ('\n'.join(': ' + line if line else ':' for line in lines) + '\n\n').encode('utf-8')


class ServerSentEventsWriter:
	"""Wrap a plain or chunked stream to send SSE events immediately."""

	def __init__(
		self,
		writer: Union[ResponseWriter, StreamWriter],
	):
		self.writer = StreamWriter(writer) if isinstance(writer, ResponseWriter) else writer
		return

	def begin(
		self,
		headers: Optional[Mapping[str, str]] = None,
	) -> None:
		properties = dict(headers) if headers is not None else {}
		if not any(key.lower() == 'cache-control' for key in properties):
			properties['Cache-Control'] = 'no-cache'
		self.writer.begin(
			headers=properties,
			format='text/event-stream',
			charset='utf-8',
		)
		return

	def emit(
		self,
		data: str,
		event: Optional[str] = None,
		id: Optional[str] = None,
		retry: Optional[int] = None,
	) -> None:
		self.writer.write(ServerSentEvents(
			data=data,
			event=event,
			id=id,
			retry=retry,
		).encode())
		self.writer.flush()
		return

	def retry(
		self,
		ms: int,
	) -> None:
		frame = ServerSentEvents(retry=ms).retry_line()
		self.writer.write((frame + '\n').encode('utf-8'))
		self.writer.flush()
		return

	def comment(
		self,
		text: str,
	) -> None:
		self.writer.write(_encode_sse_comment(text))
		self.writer.flush()
		return

	def end(self) -> None:
		self.writer.end()
		return
