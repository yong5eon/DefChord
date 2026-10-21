from dataclasses import (
	asdict,
	is_dataclass,
)
from json import dumps

from ..Response import Response
from .ResponseFile import ResponseFile


class ResponseJSON(Response):
	"""JSON 또는 dataclass 값을 UTF-8 응답으로 직렬화한다."""

	def __init__(
		self,
		value,
		status=200,
		headers=None,
	):
		def encode(value):
			if is_dataclass(value) and not isinstance(value, type):
				return asdict(value)
			raise TypeError('JSON으로 변환할 수 없는 값: ' + type(value).__name__)

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
	"""문자열을 명시적인 문자셋으로 출력한다."""

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
