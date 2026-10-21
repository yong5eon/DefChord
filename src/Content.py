from dataclasses import dataclass
from typing import (
	Any,
	Optional,
)


@dataclass(frozen=True)
class Content:
	"""입출력 콘텐츠 형식과 스키마·예시 메타데이터."""

	format: str
	schema: Optional[object] = None
	example: Any = None
