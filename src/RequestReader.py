from typing import (
	Optional,
	Protocol,
)

from .Error import ClientError


class BinaryReader(Protocol):
	def read(
		self,
		size: int = -1,
		/,
	) -> bytes:
		...

	def readline(
		self,
		size: int = -1,
		/,
	) -> bytes:
		...


class RequestReader:
	"""Remove transfer framing and read within request body boundaries."""

	def __init__(
		self,
		reader: BinaryReader,
		size: Optional[int] = None,
		chunked: bool = False,
	):
		if size is not None and size < 0:
			raise ValueError('Body length must not be negative')
		if chunked and size is not None:
			raise ClientError('Content-Length and Transfer-Encoding cannot be used together')
		self.reader = reader
		self.remaining = size if size is not None else 0
		self.chunked = chunked
		self.chunk_remaining = 0
		self.finished = not chunked and self.remaining == 0
		return

	def line(self) -> bytes:
		line = self.reader.readline(65537)
		if len(line) > 65536 or not line.endswith(b'\r\n'):
			raise ClientError('Invalid or truncated chunked framing')
		return line[:-2]

	def exact(
		self,
		size: int,
	) -> bytes:
		parts = []
		while size:
			part = self.reader.read(size)
			if not part:
				raise ClientError('Connection closed while receiving the request body')
			parts.append(part)
			size -= len(part)
		return b''.join(parts)

	def next_chunk(self) -> None:
		line = self.line()
		size = line.split(b';', 1)[0]
		if not size or any(byte not in b'0123456789abcdefABCDEF' for byte in size):
			raise ClientError('Invalid chunk size')
		self.chunk_remaining = int(size, 16)
		if self.chunk_remaining == 0:
			while True:
				trailer = self.line()
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
		return

	def read(
		self,
		size: int = -1,
	) -> bytes:
		if size < -1:
			raise ValueError('Read size must be at least -1')
		if size == 0 or self.finished:
			return b''
		if not self.chunked:
			count = self.remaining if size == -1 else min(size, self.remaining)
			data = self.exact(count)
			self.remaining -= len(data)
			self.finished = self.remaining == 0
			return data
		parts = []
		while not self.finished and (size == -1 or size > 0):
			if self.chunk_remaining == 0:
				self.next_chunk()
				if self.finished:
					break
			count = self.chunk_remaining if size == -1 else min(size, self.chunk_remaining)
			part = self.exact(count)
			parts.append(part)
			self.chunk_remaining -= count
			if size != -1:
				size -= count
			if self.chunk_remaining == 0 and self.exact(2) != b'\r\n':
				raise ClientError('Invalid chunk delimiter')
		return b''.join(parts)

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
