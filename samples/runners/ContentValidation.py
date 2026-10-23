from DefEssential import (
	Body,
	Request,
	RequestRunner,
)
from DefEssential.Readers import JavaScriptObjectNotationContentReader
from DefEssential.Responses import ResponseJSON
from DefEssential.Validator.Patterns import (
	IsArray,
	IsBool,
	IsInteger,
	IsList,
	IsNumber,
	IsObject,
	IsString,
)


class RunContentBool(
	RequestRunner,
	method='POST',
	url='/api/content/bool',
	name='RunContent(bool)',
	body=Body(JavaScriptObjectNotationContentReader(va=IsBool())),
	summary='Validate and return a JSON boolean',
	tags='Content Validation',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.body)


class RunContentInteger(
	RequestRunner,
	method='POST',
	url='/api/content/integer',
	name='RunContent(integer)',
	body=Body(JavaScriptObjectNotationContentReader(va=IsInteger())),
	summary='Validate and return a JSON integer',
	tags='Content Validation',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.body)


class RunContentNumber(
	RequestRunner,
	method='POST',
	url='/api/content/number',
	name='RunContent(number)',
	body=Body(JavaScriptObjectNotationContentReader(va=IsNumber())),
	summary='Validate and return a JSON number',
	tags='Content Validation',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.body)


class RunContentString(
	RequestRunner,
	method='POST',
	url='/api/content/string',
	name='RunContent(string)',
	body=Body(JavaScriptObjectNotationContentReader(va=IsString())),
	summary='Validate and return a JSON string',
	tags='Content Validation',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.body)


class RunContentArray(
	RequestRunner,
	method='POST',
	url='/api/content/array',
	name='RunContent(array)',
	body=Body(JavaScriptObjectNotationContentReader(va=IsList(IsArray()))),
	summary='Validate and return a JSON array',
	tags='Content Validation',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.body)


class RunContentObject(
	RequestRunner,
	method='POST',
	url='/api/content/object',
	name='RunContent(object)',
	body=Body(JavaScriptObjectNotationContentReader(va=IsObject())),
	summary='Validate and return a JSON object',
	tags='Content Validation',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.body)
