from logging import getLogger

from DefEssential import (
	Body,
	Content,
	Headers,
	Parameters,
	QueryString,
	Request,
	RequestRunner,
	RequestRunnerRequest,
	RequestRunnerRequestError,
	RequestRunnerRequestResponse,
	Response,
	ResponseSpecification,
)
from DefEssential.Descriptor import (
	Binary,
	Schema,
)
from DefEssential.IO.Readers import (
	ByteStringContentReader,
	JavaScriptObjectNotationContentReader,
)
from DefEssential.Responses import ResponseJSON
from DefEssential.Validator.Patterns import (
	IsGreaterThan,
	IsLessThan,
	IsObject,
	IsOptional,
	IsString,
	SetDefault,
	ToFloat,
	ToInteger,
)
from DefEssential.Validator.Patterns.Object import (
	IsMappingOf,
	IsRequiredIn,
)


PARAMETERS = Parameters(
	{
		'a': ToInteger(IsGreaterThan(100)),
		'b': ToInteger(IsGreaterThan(100)),
	},
	format={
		'a': {
			'type': 'integer',
			'exclusiveMinimum': 100,
			'description': 'First path value used in the calculation',
			'examples': [101],
		},
		'b': {
			'type': 'integer',
			'exclusiveMinimum': 100,
			'description': 'Second path value used in the calculation',
			'examples': [102],
		},
	},
)
QUERIES = QueryString(
	{
		'a': ToInteger(IsGreaterThan(5)),
		'b': ToFloat(IsGreaterThan(9.0)),
		'c': (
			SetDefault('안녕'),
			IsString(),
		),
	},
	requires=(
		'a',
		'b',
	),
	format={
		'a': {
			'type': 'integer',
			'exclusiveMinimum': 5,
			'examples': [6],
		},
		'b': {
			'type': 'number',
			'exclusiveMinimum': 9,
			'examples': [10],
		},
		'c': {
			'type': 'string',
			'default': '안녕',
			'description': 'Message returned with the calculation result',
		},
	},
)
JSON_BODY = Body(
	JavaScriptObjectNotationContentReader(va=IsObject(
		IsRequiredIn(
			'a',
			'b',
		),
		IsMappingOf({
			'a': ToInteger(IsLessThan(5)),
			'b': ToFloat(IsLessThan(9.0)),
		}),
	)),
	content=Content(
		'application/json',
		schema=Schema(
			'CalculationInput',
			{
				'type': 'object',
				'required': [
					'a',
					'b',
				],
				'properties': {
					'a': {
						'type': 'integer',
						'exclusiveMaximum': 5,
						'description': 'Integer used to calculate the first value',
					},
					'b': {
						'type': 'number',
						'exclusiveMaximum': 9,
						'description': 'Number used to calculate the second value',
					},
				},
			},
		),
		example={
			'a': 2,
			'b': 3,
		},
	),
)
CALCULATION_RESPONSE = ResponseSpecification(
	200,
	'Validated input and calculation result',
	Content(
		'application/json',
		schema=Schema(
			'CalculationResult',
			{
				'type': 'object',
				'required': [
					'status',
					'message',
					'data',
				],
				'properties': {
					'status': {
						'type': 'integer',
						'const': 200,
					},
					'message': {'type': 'string'},
					'data': {
						'type': 'object',
						'required': [
							'message',
							'args',
							'ret',
						],
						'properties': {
							'message': {'type': 'string'},
							'args': {
								'type': 'object',
								'description': 'Validated and converted path, query, and body input',
								'properties': {
									'parameters': {'type': 'object'},
									'qs': {'type': 'object'},
									'content': {
										'type': [
											'object',
											'null',
										],
									},
								},
							},
							'ret': {
								'type': 'number',
								'description': 'Calculation result',
							},
						},
					},
				},
			},
		),
	),
)


class RequestLog(RequestRunnerRequest):
	"""Log entry into the handler for a validated request."""

	def __call__(
		self,
		request: Request,
	) -> Request:
		getLogger('Sample.Requests').debug(
			'요청 훅: id=%s (핸들러 실행 전)',
			request.id,
		)
		return request


class ResponseLog(RequestRunnerRequestResponse):
	"""Log when a returned response is processed before transmission."""

	def __call__(
		self,
		request: Request,
		response: Response,
	) -> Response:
		getLogger('Sample.Requests').debug(
			'응답 훅: id=%s status=%s (헤더 전송 전)',
			request.id,
			response.status,
		)
		return response


class ErrorLog(RequestRunnerRequestError):
	"""Observe the types of validation and handler execution errors."""

	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> None:
		getLogger('Sample.Requests').debug(
			'오류 훅: id=%s error_type=%s',
			request.id,
			type(error).__name__,
		)
		return


def result(
	request: Request,
) -> ResponseJSON:
	parameters = request.parameters
	queries = request.qs
	left = parameters['a'] + queries['b']
	right = parameters['b'] + queries['b']
	content = request.body
	if request.method == 'POST':
		left += content['a']
		right += content['b']
	elif request.method == 'PUT':
		left = parameters['a'] + queries['b'] * content['a']
		right = parameters['b'] + queries['b'] * content['b']
	elif request.method == 'DELETE':
		left -= content['a']
		right -= content['b']
	return ResponseJSON({
		'status': 200,
		'message': 'OK',
		'data': {
			'message': queries['c'],
			'args': {
				'parameters': parameters,
				'qs': queries,
				'content': content,
			},
			'ret': left * right,
		},
	})


class RunGet(
	RequestRunner,
	method='GET',
	url='/api/run/:a/:b',
	parameters=PARAMETERS,
	qs=QUERIES,
	summary='Validate path and query values and calculate the result',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
	on_request=RequestLog(),
	on_request_response=ResponseLog(),
	on_request_error=ErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> Response:
		return result(request)


class RunPost(
	RequestRunner,
	method='POST',
	url='/api/run/:a/:b',
	parameters=PARAMETERS,
	qs=QUERIES,
	body=JSON_BODY,
	summary='Calculate the result by adding JSON body values',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
	on_request=RequestLog(),
	on_request_response=ResponseLog(),
	on_request_error=ErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> Response:
		return result(request)


class RunPut(
	RequestRunner,
	method='PUT',
	url='/api/run/:a/:b',
	parameters=PARAMETERS,
	qs=QUERIES,
	body=JSON_BODY,
	summary='Calculate the result by multiplying JSON body values',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
	on_request=RequestLog(),
	on_request_response=ResponseLog(),
	on_request_error=ErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> Response:
		return result(request)


class RunDelete(
	RequestRunner,
	method='DELETE',
	url='/api/run/:a/:b',
	parameters=PARAMETERS,
	qs=QUERIES,
	body=JSON_BODY,
	summary='Calculate the result by subtracting JSON body values',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
	on_request=RequestLog(),
	on_request_response=ResponseLog(),
	on_request_error=ErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> Response:
		return result(request)


class RunUpload(
	RequestRunner,
	method='POST',
	url='/api/run/upload',
	headers=Headers(
		{
			'Content-Format': IsString(),
			'Content-Charset': IsOptional(IsString()),
		},
		requires='Content-Format',
	),
	body=Body(
		ByteStringContentReader(),
		content=Content(
			'application/octet-stream',
			Binary(),
		),
	),
	summary='Return a binary upload in the specified format',
	tags='RequestRunner',
	on_request=RequestLog(),
	on_request_response=ResponseLog(),
	on_request_error=ErrorLog(),
):
	def run(
		self,
		request: Request,
	) -> Response:
		return Response(
			body=request.body,
			format=request.header('Content-Format'),
			charset=request.header('Content-Charset'),
		)
