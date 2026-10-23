from typing import (
	Optional,
	Protocol,
)

from ..Error import ClientError


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


class ClientDisconnected(ConnectionError):
	"""Represent a client connection lost while receiving the request body."""


class RequestReader:
	"""Read a Content-Length body and expose raw input primitives for chunked readers."""

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
		self.finished = not chunked and self.remaining == 0
		return

	def line(self) -> bytes:
		"""Read one raw CRLF-terminated line without the line ending."""
		try:
			line = self.reader.readline(65537)
		except ConnectionError as error:
			raise ClientDisconnected(*error.args) from error
		if len(line) > 65536 or not line.endswith(b'\r\n'):
			raise ClientError('Invalid or truncated body line')
		return line[:-2]

	def exact(
		self,
		size: int,
	) -> bytes:
		"""Read exactly size raw bytes."""
		parts = []
		while size:
			try:
				part = self.reader.read(size)
			except ConnectionError as error:
				raise ClientDisconnected(*error.args) from error
			if not part:
				raise ClientError('Connection closed while receiving the request body')
			parts.append(part)
			size -= len(part)
		return b''.join(parts)

	def read(
		self,
		size: int = -1,
	) -> bytes:
		if size < -1:
			raise ValueError('Read size must be at least -1')
		if self.chunked:
			raise ClientError(
				'Content-Length is required',
				status=411,
			)
		if size == 0 or self.finished:
			return b''
		count = self.remaining if size == -1 else min(size, self.remaining)
		data = self.exact(count)
		self.remaining -= len(data)
		self.finished = self.remaining == 0
		return data

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