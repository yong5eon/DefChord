from dataclasses import dataclass
from typing import (
	Any,
	Optional,
)

__all__ = (
	'Content',
)


@dataclass(frozen=True)
class Content:
	"""Describe input or output content formats, schemas, and examples."""

	format: str
	schema: Optional[object] = None
	example: Any = None
