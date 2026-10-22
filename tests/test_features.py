from io import BytesIO
from unittest import TestCase

from DefEssential import (
	Application,
	Auth,
	Authorization,
	Body,
	ClientError,
	Content,
	Headers,
	Origin,
	Parameters,
	QueryString,
	Request,
	RequestReader,
	RequestRunner,
	Response,
	ResponseWriter,
)
from DefEssential.Credentials import (
	Cookie,
	Header,
	HTTP,
	OAuth2AuthorizationCode,
	OAuth2ClientCredentials,
	OAuth2Implicit,
	OAuth2Password,
	Query,
)
from DefEssential.Readers import (
	ByteStringContentReader,
	FormUrlEncodedContentReader,
	JavaScriptObjectNotationContentReader,
	TextContentReader,
	TypeReader,
)
from DefEssential.Writers import StreamWriter
from DefEssential.Validator.Patterns import (
	IsString,
	SetDefault,
	ToInteger,
)


def request(
	uri='/',
	method='GET',
	headers=None,
	body=b'',
):
	return Request(
		address='127.0.0.1',
		port=1,
		method=method,
		uri=uri,
		headers=headers,
		reader=RequestReader(
			BytesIO(body),
			size=len(body),
		),
	)


class SessionAuthorization(Authorization):
	def __call__(
		self,
		credentials,
	):
		value = credentials.credentials if hasattr(credentials, 'credentials') else credentials
		if value != '1':
			raise ClientError(
				'인증 실패',
				status=401,
			)
		return {'id': value}


class FeatureTests(TestCase):
	def test_all_credentials_and_optional_auth(self):
		for extractor, uri, headers in (
			(Query('credentials'), '/?credentials=1', {}),
			(Header('credentials'), '/', {'Credentials': '1'}),
			(Cookie('credentials'), '/', {'Cookie': 'other=2; credentials=1'}),
			(HTTP('Bearer'), '/', {'Authorization': 'bearer 1'}),
			(OAuth2Implicit('/authorize'), '/', {'Authorization': 'Bearer 1'}),
			(OAuth2Password('/token', '/refresh'), '/', {'Authorization': 'Bearer 1'}),
			(OAuth2ClientCredentials('/token'), '/', {'Authorization': 'Bearer 1'}),
			(OAuth2AuthorizationCode('/authorize', '/token'), '/', {'Authorization': 'Bearer 1'}),
		):
			with self.subTest(extractor=type(extractor).__name__):
				req = request(
					uri,
					headers=headers,
				)
				Auth(
					SessionAuthorization(),
					extractor,
				)(req)
				self.assertEqual(
					req.session,
					{'id': '1'},
				)
				self.assertTrue(extractor.format)
		req = request()
		Auth(
			SessionAuthorization(),
			Header('credentials'),
			optional=True,
		)(req)
		self.assertIsNone(req.session)
		for headers in (
			{},
			{'Authorization': 'Basic 1'},
			{'Authorization': 'Bearer '},
			{'Authorization': 'Bearer 2'},
		):
			with self.assertRaises(ClientError):
				Auth(
					SessionAuthorization(),
					HTTP('Bearer'),
					optional=bool(headers),
				)(request(
					headers=headers,
				))
		with self.assertRaises(ClientError):
			Query('credentials')(request('/?credentials=1&credentials=2'))
		return

	def test_auth_and_required_custom_errors(self):
		error = ClientError(
			'사용자 정의 오류',
			status=403,
		)
		checks = (
			Auth(
				SessionAuthorization(),
				Header('credentials'),
				error=error,
			),
			QueryString(
				{'a': IsString()},
				requires='a',
				requiresError=error,
			),
			Headers(
				{'X-ID': IsString()},
				requires='X-ID',
				requiresError=error,
			),
			Origin(
				'https://allowed',
				error=error,
			),
		)
		for check in checks:
			with self.assertRaises(ClientError) as caught:
				check(request())
			self.assertIs(
				caught.exception,
				error,
			)
		return

	def test_mapping_conversion_required_and_case_insensitive_headers(self):
		req = request(
			'/?a=2',
			headers={'x-id': '3'},
		)
		req.params = {'p': '1'}
		Parameters({'p': ToInteger()})(req)
		QueryString(
			{
				'a': ToInteger(),
				'b': SetDefault('기본값'),
			},
			requires='a',
		)(req)
		Headers(
			{'X-ID': ToInteger()},
			requires='X-ID',
		)(req)
		self.assertEqual(req.params['p'], 1)
		self.assertEqual(req.qs, {'a': 2, 'b': '기본값'})
		self.assertEqual(req.header('X-Id'), '3')
		with self.assertRaises(ClientError):
			Parameters({'p': ToInteger()})(request())
		return

	def test_parser_options_and_content(self):
		parse_error = ClientError('파싱 오류', status=422)
		type_error = ClientError('형식 오류', status=415)
		for reader, body, mime, expected_error in (
			(JavaScriptObjectNotationContentReader(error=parse_error), b'{', 'application/json', parse_error),
			(TextContentReader(error=parse_error), b'\xff', 'text/plain', parse_error),
			(JavaScriptObjectNotationContentReader(error=parse_error, typeerror=type_error), b'1', 'text/plain', type_error),
		):
			with self.assertRaises(ClientError) as caught:
				Body(reader)(request(
					method='POST',
					headers={'Content-Type': mime},
					body=body,
				))
			self.assertIs(caught.exception, expected_error)
		reader = JavaScriptObjectNotationContentReader(typereader=lambda value: str(value))
		self.assertEqual(
			Body(reader)(request(
				headers={'Content-Type': 'application/json'},
				body=b'{"a":[1,true]}',
			)),
			{'a': ['1', 'True']},
		)
		self.assertEqual(
			Body(FormUrlEncodedContentReader())(request(
				headers={'Content-Type': 'application/x-www-form-urlencoded'},
				body=b'a=x%252By&b=1&b=2&c=',
			)),
			{'a': 'x%2By', 'b': ['1', '2'], 'c': ''},
		)
		with self.assertRaises(ClientError):
			Body(
				TextContentReader(),
				content=Content('text/html'),
			)(request(
				headers={'Content-Type': 'text/plain'},
				body=b'text',
			))
		return

	def test_each_parser_validator_custom_errors_and_type_reader(self):
		for reader, body, mime in (
			(ByteStringContentReader, b'body', 'application/octet-stream'),
			(TextContentReader, b'body', 'text/plain'),
			(FormUrlEncodedContentReader, b'a=1', 'application/x-www-form-urlencoded'),
			(JavaScriptObjectNotationContentReader, b'{}', 'application/json'),
		):
			validation_error = ClientError('값 검증 실패', status=422)
			parser = reader(
				va=ToInteger(),
				error=validation_error,
			)
			with self.assertRaises(ClientError) as caught:
				Body(parser)(request(
					body=body,
					headers={'Content-Type': mime},
				))
			self.assertIs(caught.exception, validation_error)
			type_error = ClientError('본문 형식 오류', status=415)
			parser = reader(typeerror=type_error)
			with self.assertRaises(ClientError) as caught:
				Body(parser)(request(
					body=b'body',
					headers={'Content-Type': 'application/unknown'},
				))
			self.assertIs(caught.exception, type_error)

		class Convert(TypeReader):
			def __call__(
				self,
				value,
			):
				return value + 1

		self.assertEqual(
			Body(JavaScriptObjectNotationContentReader(typereader=Convert()))(request(
				body=b'1',
				headers={'Content-Type': 'application/json'},
			)),
			2,
		)
		return

	def test_cors_is_applied_to_direct_output_and_early_filter_response(self):
		def early(req):
			return req, Response(body=b'early')

		class Direct(
			RequestRunner,
			method='GET',
			url='/direct',
			origin=Origin(all=True),
		):
			def run(
				self,
				req,
			):
				writer = StreamWriter(req.writer)
				writer.begin()
				writer.write(b'direct')
				writer.end()
				return

		class Early(
			RequestRunner,
			method='GET',
			url='/early',
			origin=Origin(all=True),
			onRequest=early,
		):
			def run(
				self,
				req,
			):
				raise AssertionError('요청 필터에서 응답해야 합니다')

		app = Application()
		app.add(Direct)
		app.add(Early)
		sent = []
		req = request(
			'/direct',
			headers={'Origin': 'https://client'},
		)
		req.response_writer = ResponseWriter(
			lambda response, chunked: sent.append(response),
			BytesIO(),
		)
		self.assertIsNone(app(req))
		self.assertEqual(sent[0].header('Access-Control-Allow-Origin'), 'https://client')
		response = app(request(
			'/early',
			headers={'Origin': 'https://client'},
		))
		assert isinstance(response, Response)
		self.assertEqual(response.body, b'early')
		self.assertEqual(response.header('Access-Control-Allow-Origin'), 'https://client')
		return

	def test_cors_actual_preflight_options_and_app_isolation(self):
		class Secured(
			RequestRunner,
			method='POST',
			url='/',
			origin=(
				Origin('https://allowed'),
				Origin('https://other'),
			),
			auth=Auth(
				SessionAuthorization(),
				HTTP('Bearer'),
			),
			headers=Headers({'X-ID': IsString()}),
			body=Body(JavaScriptObjectNotationContentReader()),
		):
			def run(
				self,
				req,
			):
				return Response(headers={'X-Result': 'yes'})

		app = Application()
		app.add(Secured)
		response = app(request(
			method='POST',
			headers={
				'Origin': 'https://other',
				'Authorization': 'Bearer 1',
				'X-ID': 'sample',
				'Content-Type': 'application/json',
			},
			body=b'{}',
		))
		assert isinstance(response, Response)
		self.assertEqual(response.header('Access-Control-Allow-Origin'), 'https://other')
		self.assertEqual(response.header('Access-Control-Allow-Credentials'), 'true')
		exposed = response.header('Access-Control-Expose-Headers')
		assert exposed is not None
		self.assertIn('X-Result', exposed)
		response = app(request(
			method='OPTIONS',
			headers={
				'Origin': 'https://allowed',
				'Access-Control-Request-Method': 'POST',
				'Access-Control-Request-Headers': 'authorization, content-type, x-id',
			},
		))
		assert isinstance(response, Response)
		self.assertEqual(response.status, 204)
		self.assertEqual(response.header('Access-Control-Allow-Methods'), 'POST')
		vary = response.header('Vary')
		assert vary is not None
		self.assertIn('Origin', vary)
		for headers, status in (
			({'Origin': 'https://denied', 'Access-Control-Request-Method': 'POST'}, 403),
			({'Origin': 'https://allowed', 'Access-Control-Request-Method': 'DELETE'}, 405),
			({'Origin': 'https://allowed', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'X-Unknown'}, 400),
		):
			with self.assertRaises(ClientError) as caught:
				app(request(method='OPTIONS', headers=headers))
			self.assertEqual(caught.exception.status, status)
		options = app(request(method='OPTIONS'))
		assert isinstance(options, Response)
		self.assertEqual(options.header('Allow'), 'OPTIONS, POST')
		options = app(request('*', method='OPTIONS'))
		assert isinstance(options, Response)
		self.assertEqual(options.status, 204)
		with self.assertRaises(ClientError):
			Application()(request(method='OPTIONS'))
		return
