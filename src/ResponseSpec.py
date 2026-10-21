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
	"""실제 Response와 분리된 OpenAPI 응답 선언."""

	status: int
	description: str
	content: Union[Content, Sequence[Content], None] = None
	headers: Optional[Mapping[str, object]] = None
