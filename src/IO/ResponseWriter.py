from typing import (
	Callable,
	Optional,
	Protocol,
)

from ..Response import (
	Response,
	close_bodies,
)
from ..Error import ClientError

__all__ = (
	'BinaryWriter',
	'ResponseWriter',
)


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
	"""Share response state to prevent duplicate direct and returned responses."""

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
		self.status = 500
		self.ended = False
		self.failed = False
		self.chunked = False
		self.suppress_body = False
		self.on_request_response: Optional[Callable[[Response], Response]] = None
		return

	def start(
		self,
		response: Response,
		chunked: bool,
	) -> None:
		if self.started:
			raise RuntimeError('Cannot start a response that has already started')
		if not 200 <= response.status <= 599:
			raise ValueError('Final response status code must be between 200 and 599')
		self.chunked = chunked
		self.suppress_body = self.method == 'HEAD' or response.status in (
			204,
			205,
			304,
		)
		if chunked and not self.suppress_body and self.version != 'HTTP/1.1':
			raise ClientError('Chunked output requires an HTTP/1.1 request')
		self.started = True
		self.status = response.status
		try:
			self.sender(
				response,
				chunked,
			)
		except Exception:
			self.failed = True
			raise
		return

	def filter(
		self,
		response: Response,
	) -> Response:
		"""Call the injected response hook and validate a response for direct output."""
		if self.on_request_response is not None:
			response = self.on_request_response(response)
		if not isinstance(response, Response):
			raise TypeError('Response hooks must return a Response')
		try:
			if not isinstance(response.body, bytes) or response.body:
				raise ValueError('Response hooks must not set a body for direct output')
			if response.header('Content-Length') is not None:
				raise ValueError('Content-Length must not be set for direct output')
		except Exception:
			close_bodies(
				response.body,
				preserve_error=True,
			)
			raise
		return response

	def begin(
		self,
		response: Response,
		chunked: bool = False,
	) -> None:
		"""Send direct-output response headers once, after running response hooks and validation."""
		if self.started:
			raise RuntimeError('Cannot start a response that has already started')
		self.start(
			self.filter(response),
			chunked,
		)
		return

	def upgrade(
		self,
		response: Response,
	) -> None:
		"""Send 101 Switching Protocols headers once through the response hook.

		Subsequent write() calls send bytes without HTTP framing; the caller is
		responsible for framing the upgraded protocol.
		"""
		if self.started:
			raise RuntimeError('Cannot start a response that has already started')
		if response.status != 101:
			raise ValueError('Protocol upgrades require status 101')
		response = self.filter(response)
		if response.status != 101:
			raise ValueError('Response hooks must keep status 101 for protocol upgrades')
		self.chunked = False
		self.suppress_body = False
		self.started = True
		self.status = response.status
		try:
			self.sender(
				response,
				False,
			)
		except Exception:
			self.failed = True
			raise
		return

	def require_open(self) -> None:
		if not self.started:
			raise RuntimeError('Response must be started first')
		if self.ended or self.failed:
			raise RuntimeError('Cannot write to a completed or failed response')
		return

	def write(
		self,
		data: bytes,
	) -> None:
		"""Write bytes immediately using the current response framing."""
		self.require_open()
		if not isinstance(data, bytes):
			raise TypeError('Response streams require bytes')
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
					raise OSError('Response write made no valid progress')
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
		"""Send the terminating chunk exactly once on successful completion."""
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
		"""Send returned bytes or iterable responses through the same transport boundary."""
		if self.started:
			raise RuntimeError('Cannot send a response that has already started')
		if not filtered and self.on_request_response is not None:
			response = self.on_request_response(response)
		if not isinstance(response, Response):
			raise TypeError('Response hooks must return a Response')
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
