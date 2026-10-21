from DefStar import (
	Body,
	Request,
	RequestRunner,
)
from DefStar.Readers import JavaScriptObjectNotationContentReader
from DefStar.Responses import ResponseJSON
from DefStar.Validator import Pattern
from DefStar.Validator.Patterns import (
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
		summary='JSON 값의 타입을 검증하고 반환',
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
