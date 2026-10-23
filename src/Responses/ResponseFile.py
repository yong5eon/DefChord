from mimetypes import guess_type
from pathlib import Path
from typing import (
	Iterator,
	Optional,
)

from ..Error import ClientError
from ..Response import Response

__all__ = (
	'FileBody',
	'ResponseFile',
)


def file_error(error: OSError) -> ClientError:
	if isinstance(
		error,
		(
			FileNotFoundError,
			NotADirectoryError,
			IsADirectoryError,
		),
	):
		return ClientError(
			'File not found',
			status=404,
		)
	if isinstance(error, PermissionError):
		return ClientError(
			'File access denied',
			status=403,
		)
	raise error


class FileBody:
	"""Read an open file in fixed-size chunks and close it when the response ends."""

	def __init__(
		self,
		file,
	):
		self.file = file
		self.closed = False
		return

	def __iter__(self) -> Iterator[bytes]:
		try:
			while True:
				data = self.file.read(65536)
				if not data:
					break
				yield data
		finally:
			self.close()
		return

	def close(self) -> None:
		if not self.closed:
			self.closed = True
			self.file.close()
		return


class ResponseFile(Response):
	"""Stream a local file or an open FileSystemObject file as a response."""

	def __init__(
		self,
		file,
		format: Optional[str] = None,
		encoding: Optional[str] = None,
	):
		if isinstance(
			file,
			(
				str,
				Path,
			),
		):
			path = Path(file)
			try:
				file = path.open('rb')
			except (
				FileNotFoundError,
				NotADirectoryError,
				IsADirectoryError,
				PermissionError,
			) as error:
				raise file_error(error) from error
			mime, compression = guess_type(str(path))
			if format is None:
				format = mime
			if encoding is None:
				encoding = compression
		body = FileBody(file)
		try:
			super().__init__(
				body=body,
				format=format if format is not None else 'application/octet-stream',
				headers={'Content-Encoding': encoding} if encoding is not None else None,
			)
		except Exception:
			body.close()
			raise
		return
