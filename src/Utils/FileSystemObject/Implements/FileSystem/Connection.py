from email.utils import formatdate
from hashlib import sha256
from mimetypes import guess_type
from pathlib import (
	Path,
	PureWindowsPath,
)

from ...Connection import Connection as BaseConnection
from .Configuration import Configuration
from .File import File

__all__ = (
	'Connection',
)


class Connection(BaseConnection):
	"""Provide local filesystem access restricted to the configured root."""

	def __init__(
		self,
		conf: Configuration,
	):
		self.conf = conf
		self.base = Path(conf.base).resolve(strict=True)
		if not self.base.is_dir():
			raise NotADirectoryError(str(self.base))
		return

	def resolve(
		self,
		path: str,
	) -> Path:
		if '\x00' in path or '\\' in path or PureWindowsPath(path).drive or ':' in path:
			raise PermissionError('File path not allowed')
		target = (self.base / path.lstrip('/')).resolve()
		try:
			target.relative_to(self.base)
		except ValueError as error:
			raise PermissionError('Cannot access paths outside the filesystem root') from error
		return target

	def connect(self):
		return

	def exist(
		self,
		path,
	):
		return self.resolve(path).is_file()

	def type(
		self,
		path,
	):
		return guess_type(str(self.resolve(path)))

	def timestamp(
		self,
		path,
	):
		return self.resolve(path).stat().st_mtime

	def modified(
		self,
		path,
	):
		return formatdate(
			self.timestamp(path),
			usegmt=True,
		)

	def etag(
		self,
		path,
	):
		stats = self.resolve(path).stat()
		return sha256(
			'{}:{}'.format(
				stats.st_mtime_ns,
				stats.st_size,
			).encode(),
		).hexdigest()

	def size(
		self,
		path,
	):
		return self.resolve(path).stat().st_size

	def open(
		self,
		path,
		mode='r',
		encoding=None,
	):
		file = File(self)
		return file.open(
			path,
			mode=mode,
			encoding=encoding,
		)

	def close(self):
		return

	def files(
		self,
		path,
	):
		return [
			str(file.relative_to(self.base))
			for file in sorted(self.resolve(path).iterdir())
		]
