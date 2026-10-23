from ...Error import ClientError
from ..RequestReader import RequestReader

__all__ = (
	'ChunkedStream',
)


class ChunkedStream:
	"""Decode HTTP/1.1 chunked transfer coding from raw request input."""

	def __init__(
		self,
		reader: RequestReader,
	):
		if not reader.chunked:
			raise ValueError('ChunkedStream requires a chunked request body')
		self.reader = reader
		self.remaining = 0
		self.finished = reader.finished
		return

	def next_chunk(self) -> None:
		line = self.reader.line()
		size = line.split(b';', 1)[0]
		if not size or any(byte not in b'0123456789abcdefABCDEF' for byte in size):
			raise ClientError('Invalid chunk size')
		self.remaining = int(size, 16)
		if self.remaining == 0:
			while True:
				trailer = self.reader.line()
				if not trailer:
					break
				name, separator, _ = trailer.partition(b':')
				if not separator or name.lower() in (
					b'content-length',
					b'transfer-encoding',
					b'host',
				):
					raise ClientError('Invalid chunked trailer')
			self.finished = True
			self.reader.finished = True
		return

	def take(
		self,
		size: int,
	) -> bytes:
		data = self.reader.exact(size)
		self.remaining -= size
		if self.remaining == 0 and self.reader.exact(2) != b'\r\n':
			raise ClientError('Invalid chunk delimiter')
		return data

	def read(
		self,
		size: int = -1,
	) -> bytes:
		if size < -1:
			raise ValueError('Read size must be at least -1')
		if self.reader.decoded:
			data = self.reader.read(size)
			self.finished = self.reader.finished
			return data
		parts = []
		while not self.finished and (size == -1 or size > 0):
			if self.remaining == 0:
				self.next_chunk()
				if self.finished:
					break
			part = self.take(self.remaining if size == -1 else min(size, self.remaining))
			parts.append(part)
			if size != -1:
				size -= len(part)
		return b''.join(parts)

	def chunk(
		self,
		size: int = -1,
	) -> bytes:
		"""Read up to size bytes without crossing the current chunk boundary."""
		if size < -1:
			raise ValueError('Read size must be at least -1')
		if self.reader.decoded:
			return self.read(size)
		if size == 0 or self.finished:
			return b''
		if self.remaining == 0:
			self.next_chunk()
			if self.finished:
				return b''
		return self.take(self.remaining if size == -1 else min(size, self.remaining))

	def readline(
		self,
		size: int = -1,
	) -> bytes:
		parts = []
		while size == -1 or len(parts) < size:
			byte = self.read(1)
			if not byte:
				break
			parts.append(byte)
			if byte == b'\n':
				break
		return b''.join(parts)
