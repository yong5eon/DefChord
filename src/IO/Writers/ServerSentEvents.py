from dataclasses import dataclass
from typing import Optional

__all__ = (
	'ServerSentEvents',
)


@dataclass(frozen=True)
class ServerSentEvents:
	"""Encode UTF-8 SSE events for both direct writes and iterable output."""

	data: str = ''
	event: Optional[str] = None
	id: Optional[str] = None
	retry: Optional[int] = None

	@staticmethod
	def comment(
		text: str,
	) -> bytes:
		lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
		return ('\n'.join(': ' + line if line else ':' for line in lines) + '\n\n').encode('utf-8')

	def retry_line(self) -> str:
		"""Return a validated reconnection delay field."""
		if self.retry is None:
			return ''
		if isinstance(self.retry, bool) or not isinstance(self.retry, int) or self.retry < 0:
			raise ValueError('SSE retry must be a non-negative integer')
		return 'retry: ' + str(self.retry) + '\n'

	def encode(self) -> bytes:
		lines = []
		for name, value in (
			('event', self.event),
			('id', self.id),
		):
			if value is None:
				continue
			if '\r' in value or '\n' in value or (name == 'id' and '\x00' in value):
				raise ValueError('Invalid SSE ' + name)
			lines.append(name + ': ' + value)
		if self.retry is not None:
			lines.append(self.retry_line().rstrip('\n'))
		data = self.data.replace('\r\n', '\n').replace('\r', '\n')
		lines.extend('data: ' + line for line in data.split('\n'))
		return ('\n'.join(lines) + '\n\n').encode('utf-8')
