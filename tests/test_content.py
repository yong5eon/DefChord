from io import BytesIO
from unittest import TestCase

from DefEssential import (
	Application,
	Body,
	ClientError,
	Content,
	Request,
	RequestReader,
	RequestRunner,
	Response,
)
from DefEssential.Readers import (
	ByteStringContentReader,
	FormUrlEncodedContentReader,
	JavaScriptObjectNotationContentReader,
	StreamContentReader,
	TextContentReader,
)


class ContentTests(TestCase):
	def test_content_format_validation(self):
		body = Body(
			ByteStringContentReader(),
			content=Content('application/octet-stream'),
		)
		req = self.request(
			b'body',
			'Application/Octet-Stream; charset=utf-8',
		)
		self.assertEqual(body(req), b'body')
		for format, status in (
			('text/plain', 415),
			('bad-format', 400),
		):
			with self.subTest(format=format):
				with self.assertRaises(ClientError) as caught:
					body(self.request(
						b'body',
						format,
					))
				self.assertEqual(caught.exception.status, status)
		req = Request(
			address='127.0.0.1',
			port=1,
			method='POST',
			uri='/',
			reader=RequestReader(
				BytesIO(b'body'),
				size=4,
			),
		)
		with self.assertRaises(ClientError) as caught:
			body(req)
		self.assertEqual(caught.exception.status, 400)
		return

	def request(
		self,
		body,
		format,
	):
		return Request(
			address='127.0.0.1',
			port=1,
			method='POST',
			uri='/',
			headers={'Content-Type': format},
			reader=RequestReader(
				BytesIO(body),
				size=len(body),
			),
		)

	def test_all_supported_readers(self):
		for reader, body, format, expected in (
			(ByteStringContentReader(), b'\x00\xff', 'application/octet-stream', b'\x00\xff'),
			(TextContentReader(), '본문'.encode(), 'text/plain; charset=utf-8', '본문'),
			(FormUrlEncodedContentReader(), b'a=1&a=2&b=x%2520y', 'application/x-www-form-urlencoded', {'a': ['1', '2'], 'b': 'x%20y'}),
			(JavaScriptObjectNotationContentReader(), b'{"value": 1}', 'application/json', {'value': 1}),
		):
			with self.subTest(reader=type(reader).__name__):
				req = self.request(
					body,
					format,
				)
				self.assertEqual(
					Body(reader)(req),
					expected,
				)
		return

	def test_stream_does_not_read_ahead(self):
		source = BytesIO(b'body')
		req = self.request(
			b'body',
			'application/octet-stream',
		)
		req.reader = RequestReader(
			source,
			size=4,
		)
		stream = Body(StreamContentReader())(req)
		self.assertIs(
			stream,
			req.reader,
		)
		self.assertEqual(
			source.tell(),
			0,
		)
		return

	def test_invalid_content(self):
		for reader, body, format in (
			(JavaScriptObjectNotationContentReader(), b'{', 'application/json'),
			(TextContentReader(), b'\xff', 'text/plain; charset=utf-8'),
			(TextContentReader(), b'a', 'text/plain; charset=does-not-exist'),
			(JavaScriptObjectNotationContentReader(), b'{}', 'text/plain'),
			(ByteStringContentReader(), b'a', 'bad-format'),
		):
			with self.subTest(format=format):
				with self.assertRaises(ClientError):
					Body(reader)(self.request(
						body,
						format,
					))
		return

	def test_required_body_and_explicit_reader(self):
		req = self.request(
			b'',
			'application/octet-stream',
		)
		with self.assertRaises(ClientError):
			Body(ByteStringContentReader())(req)
		self.assertIsNone(Body(
			ByteStringContentReader(),
			required=False,
		)(req))

		class Sample(
			RequestRunner,
			method='POST',
			url='/',
		):
			def run(
				self,
				request,
			):
				return Response()

		app = Application()
		app.add(Sample)
		with self.assertRaises(ClientError) as caught:
			app(self.request(
				b'a',
				'application/octet-stream',
			))
		self.assertEqual(
			caught.exception.status,
			415,
		)
		return
