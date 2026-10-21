from dataclasses import (
	asdict,
	is_dataclass,
)
from json import dumps

from ..Response import Response
from .ResponseFile import ResponseFile


class ResponseJSON(Response):
	"""Serialize JSON or dataclass values as UTF-8 responses."""

	def __init__(
		self,
		value,
		status=200,
		headers=None,
	):
		def encode(value):
			if is_dataclass(value) and not isinstance(value, type):
				return asdict(value)
			raise TypeError('Value is not JSON serializable: ' + type(value).__name__)

		super().__init__(
			status=status,
			headers=headers,
			body=dumps(
				value,
				default=encode,
				ensure_ascii=False,
				allow_nan=False,
			).encode('utf-8'),
			format='application/json',
			charset='utf-8',
		)
		return


class ResponseText(Response):
	"""Encode a string using an explicit charset."""

	def __init__(
		self,
		text,
		status=200,
		headers=None,
		charset='utf-8',
	):
		super().__init__(
			status=status,
			headers=headers,
			body=text.encode(charset),
			format='text/plain',
			charset=charset,
		)
		return


__all__ = (
	'ResponseFile',
	'ResponseJSON',
	'ResponseText',
)
