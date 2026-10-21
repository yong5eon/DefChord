# -*- coding: utf-8 -*-

from ...File import File as BaseFile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .Connection import Connection

__all__ = (
	'File',
)


class File(BaseFile):
	"""로컬 파일 핸들의 수명과 읽기·쓰기를 관리한다."""

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
			raise RuntimeError('이미 열린 파일입니다')
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
			raise RuntimeError('닫힌 파일입니다')
		return self.fo.read(size if size is not None else -1)

	def write(
		self,
		buffer,
	):
		if self.fo is None:
			raise RuntimeError('닫힌 파일입니다')
		self.fo.write(buffer)
		return

	def close(self):
		if self.fo:
			self.fo.close()
			self.fo = None
		return
