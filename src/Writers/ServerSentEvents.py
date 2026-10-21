from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ServerSentEvents:
	"""직접 쓰기와 iterable 출력에 공통으로 사용하는 UTF-8 SSE 이벤트."""

	data: str = ''
	event: Optional[str] = None
	id: Optional[str] = None
	retry: Optional[int] = None

	def retry_line(self) -> str:
		"""검증된 재연결 대기 시간 필드를 반환한다."""
		if self.retry is None:
			return ''
		if isinstance(self.retry, bool) or not isinstance(self.retry, int) or self.retry < 0:
			raise ValueError('SSE retry에는 음수가 아닌 정수가 필요합니다')
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
				raise ValueError('잘못된 SSE ' + name)
			lines.append(name + ': ' + value)
		if self.retry is not None:
			lines.append(self.retry_line().rstrip('\n'))
		data = self.data.replace('\r\n', '\n').replace('\r', '\n')
		lines.extend('data: ' + line for line in data.split('\n'))
		return ('\n'.join(lines) + '\n\n').encode('utf-8')
