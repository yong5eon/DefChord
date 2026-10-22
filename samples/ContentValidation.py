from DefEssential import (
	Body,
	Request,
	RequestRunner,
)
from DefEssential.Readers import JavaScriptObjectNotationContentReader
from DefEssential.Responses import ResponseJSON
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


def content_handler(
	url: str,
	pattern: Pattern,
):
	class RunContent(
		RequestRunner,
		method='POST',
		url=url,
		body=Body(JavaScriptObjectNotationContentReader(va=pattern)),
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
	content_handler(
		'/api/content/' + name,
		pattern,
	)
	for name, pattern in (
		('bool', IsBool()),
		('integer', IsInteger()),
		('number', IsNumber()),
		('string', IsString()),
		('array', IsList(IsArray())),
		('object', IsObject()),
	)
)
