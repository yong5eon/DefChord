from typing import Type

from DefEssential import (
	Body,
	Request,
	RequestRunner,
)
from DefEssential.Readers import JavaScriptObjectNotationContentReader
from DefEssential.Responses import ResponseJSON
from DefEssential.Runners.RunFactory import RunFactory
from DefEssential.Validator import Pattern
from DefEssential.Validator.Patterns import (
	IsArray,
	IsBool,
	IsInteger,
	IsList,
	IsNumber,
	IsObject,
	IsString,
)


class RunContentFactory(RunFactory[Type[RequestRunner]]):
	"""Create a named JSON validation handler for a sample pattern."""

	def __init__(
		self,
		name: str,
		pattern: Pattern,
	):
		self.name = name
		self.pattern = pattern
		return

	def __call__(self) -> Type[RequestRunner]:
		class RunContent(
			RequestRunner,
			method='POST',
			url='/api/content/' + self.name,
			name=f'RunContent({self.name})',
			body=Body(JavaScriptObjectNotationContentReader(va=self.pattern)),
			summary='Validate and return a JSON value',
			tags='Content Validation',
		):
			def run(
				self,
				request: Request,
			) -> ResponseJSON:
				return ResponseJSON(request.body)

		return RunContent


HANDLERS = tuple(
	RunContentFactory(
		name,
		pattern,
	)()
	for name, pattern in (
		('bool', IsBool()),
		('integer', IsInteger()),
		('number', IsNumber()),
		('string', IsString()),
		('array', IsList(IsArray())),
		('object', IsObject()),
	)
)
