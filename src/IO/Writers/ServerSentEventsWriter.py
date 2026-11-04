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
		text = text.replace('\r\n', '\n').replace('\r', '\n')
		frame = '\n'.join(': ' + line for line in text.split('\n')) + '\n\n'
		self.writer.write(frame.encode('utf-8'))
		self.writer.flush()
		return

	def end(self) -> None:
		self.writer.end()
		return
