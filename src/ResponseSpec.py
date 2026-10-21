from dataclasses import dataclass
from typing import (
	Mapping,
	Optional,
	Sequence,
	Union,
)

from .Content import Content


@dataclass(frozen=True)
class ResponseSpec:
	"""Declare an OpenAPI response independently of the actual Response."""

	status: int
	description: str
	content: Union[Content, Sequence[Content], None] = None
	headers: Optional[Mapping[str, object]] = None
