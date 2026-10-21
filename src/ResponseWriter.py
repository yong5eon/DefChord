from typing import (
	Callable,
	Optional,
	Protocol,
)

from .Response import Response
from .Error import ClientError


class BinaryWriter(Protocol):
	def write(
		self,
		data: bytes,
		/,
	) -> int:
		...

	def flush(self) -> None:
		...


class ResponseWriter:
	"""응답 시작과 전송 상태를 공유해 직접 출력과 반환 응답의 중복을 막는다."""

	def __init__(
		self,
		sender: Callable[[Response, bool], None],
		writer: BinaryWriter,
		method: str = 'GET',
		version: str = 'HTTP/1.1',
	):
		self.sender = sender
		self.writer = writer
		self.method = method
		self.version = version
		self.started = False
		self.ended = False
		self.failed = False
		self.chunked = False
		self.suppress_body = False
		self.on_response: Optional[Callable[[Response], Response]] = None
		return

	def start(
		self,
		response: Response,
		chunked: bool,
	) -> None:
		if self.started:
			raise RuntimeError('이미 시작한 응답을 다시 시작할 수 없습니다')
		if not 200 <= response.status <= 599:
			raise ValueError('최종 응답에는 200~599 상태 코드가 필요합니다')
		self.chunked = chunked
		self.suppress_body = self.method == 'HEAD' or response.status in (
			204,
			205,
			304,
		)
		if chunked and not self.suppress_body and self.version != 'HTTP/1.1':
			raise ClientError('Chunked 출력에는 HTTP/1.1 요청이 필요합니다')
		self.started = True
		try:
			self.sender(
				response,
				chunked,
			)
		except Exception:
			self.failed = True
			raise
		return

	def begin(
		self,
		response: Response,
		chunked: bool = False,
	) -> None:
		"""직접 출력의 헤더를 필터링한 뒤 한 번만 전송한다."""
		if self.started:
			raise RuntimeError('이미 시작한 응답을 다시 시작할 수 없습니다')
		if self.on_response is not None:
			response = self.on_response(response)
		if not isinstance(response, Response):
			raise TypeError('응답 필터는 Response를 반환해야 합니다')
		if not isinstance(response.body, bytes) or response.body:
			raise ValueError('직접 출력의 응답 필터는 본문을 지정할 수 없습니다')
		if response.header('Content-Length') is not None:
			raise ValueError('직접 출력에는 Content-Length를 지정할 수 없습니다')
		self.start(
			response,
			chunked,
		)
		return

	def require_open(self) -> None:
		if not self.started:
			raise RuntimeError('먼저 응답을 시작해야 합니다')
		if self.ended or self.failed:
			raise RuntimeError('종료되었거나 실패한 응답에는 쓸 수 없습니다')
		return

	def write(
		self,
		data: bytes,
	) -> None:
		"""현재 응답의 프레이밍에 맞춰 바이트를 즉시 쓴다."""
		self.require_open()
		if not isinstance(data, bytes):
			raise TypeError('응답 스트림에는 bytes가 필요합니다')
		if not data or self.suppress_body:
			return
		if self.chunked:
			data = format(len(data), 'x').encode('ascii') + b'\r\n' + data + b'\r\n'
		self.write_bytes(data)
		return

	def write_bytes(
		self,
		data: bytes,
	) -> None:
		try:
			while data:
				count = self.writer.write(data)
				if count <= 0 or count > len(data):
					raise OSError('응답 쓰기가 진행되지 않았습니다')
				data = data[count:]
		except Exception:
			self.failed = True
			raise
		return

	def flush(self) -> None:
		self.require_open()
		try:
			self.writer.flush()
		except Exception:
			self.failed = True
			raise
		return

	def end(self) -> None:
		"""정상 종료 시 Chunked 종료 프레임을 한 번만 전송한다."""
		if self.ended:
			return
		self.require_open()
		if self.chunked and not self.suppress_body:
			self.write_bytes(b'0\r\n\r\n')
		self.flush()
		self.ended = True
		return

	def response(
		self,
		response: Response,
		*,
		filtered: bool = False,
	) -> None:
		"""반환된 bytes 또는 iterable 응답을 동일한 전송 경계로 출력한다."""
		if self.started:
			raise RuntimeError('이미 시작한 응답을 다시 전송할 수 없습니다')
		if not filtered and self.on_response is not None:
			response = self.on_response(response)
		if not isinstance(response, Response):
			raise TypeError('응답 필터는 Response를 반환해야 합니다')
		if isinstance(response.body, bytes) and response.status not in (
			204,
			205,
			304,
		):
			response.header(
				'Content-Length',
				str(len(response.body)),
			)
		else:
			del response.props['Content-Length']
		self.start(
			response,
			False,
		)
		if not self.suppress_body:
			if isinstance(response.body, bytes):
				self.write(response.body)
			else:
				for data in response.body:
					self.write(data)
					self.flush()
		self.end()
		return
