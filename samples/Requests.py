from DefStar import (
	Body,
	Content,
	Headers,
	Parameters,
	QueryString,
	Request,
	RequestRunner,
	Response,
	ResponseSpec,
)
from DefStar.Descriptor import Schema
from DefStar.Readers import (
	ByteStringContentReader,
	JavaScriptObjectNotationContentReader,
)
from DefStar.Responses import ResponseJSON
from DefStar.Validator.Patterns import (
	IsGreaterThan,
	IsLessThan,
	IsObject,
	IsOptional,
	IsString,
	SetDefault,
	ToFloat,
	ToInteger,
)
from DefStar.Validator.Patterns.Object import (
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
			'description': '계산에 사용할 첫 번째 경로 값',
			'examples': [101],
		},
		'b': {
			'type': 'integer',
			'exclusiveMinimum': 100,
			'description': '계산에 사용할 두 번째 경로 값',
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
			'description': '계산 결과에 함께 반환할 메시지',
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
						'description': '첫 번째 값의 계산에 사용할 정수',
					},
					'b': {
						'type': 'number',
						'exclusiveMaximum': 9,
						'description': '두 번째 값의 계산에 사용할 숫자',
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
CALCULATION_RESPONSE = ResponseSpec(
	200,
	'검증된 입력과 계산 결과',
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
								'description': '검증·변환된 경로·쿼리·본문 입력',
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
								'description': '계산 결과',
							},
						},
					},
				},
			},
		),
	),
)


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
	summary='경로·쿼리 검증과 계산',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
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
	summary='JSON 본문을 더하는 계산',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
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
	summary='JSON 본문을 곱하는 계산',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
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
	summary='JSON 본문을 빼는 계산',
	response=CALCULATION_RESPONSE,
	tags='RequestRunner',
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
	body=Body(ByteStringContentReader()),
	summary='바이너리 업로드를 지정한 형식으로 반환',
	tags='RequestRunner',
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
