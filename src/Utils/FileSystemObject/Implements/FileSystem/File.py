# -*- coding: utf-8 -*-

from ...File import File as BaseFile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .Connection import Connection

__all__ = (
	'File',
)


class File(BaseFile):
	"""Manage local file handle lifetime, reading, and writing."""

	def __init__(
		self,
		fso: 'Connection',
	):
		self.fso: 'Connection' = fso
		self.fo = None
		return

	def __del__(self):
		if self.fo:
			self.close()
		return

	def __enter__(self):
		return self

	def __exit__(
		self,
		exc_type,
		exc_val,
		exc_tb,
	):
		self.close()
		return

	def open(
		self,
		path,
		mode='r',
		encoding=None,
	):
		if self.fo is not None:
			raise RuntimeError('File is already open')
		self.fo = self.fso.resolve(path).open(
			mode,
			encoding=encoding,
		)
		return self

	def read(
		self,
		size=None,
	):
		if self.fo is None:
			raise RuntimeError('File is closed')
		return self.fo.read(size if size is not None else -1)

	def write(
		self,
		buffer,
	):
		if self.fo is None:
			raise RuntimeError('File is closed')
		self.fo.write(buffer)
		return

	def close(self):
		if self.fo:
			self.fo.close()
			self.fo = None
		return
