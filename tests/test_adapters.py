from asyncio import run
from io import BytesIO
from unittest import TestCase

from DefEssential import (
	Application,
	Body,
	RequestRunner,
	Response,
)
from DefEssential.Adapter.Implements.Gunicorn import GunicornAdapter
from DefEssential.Adapter.Implements.Uvicorn import UvicornAdapter
from DefEssential.Readers import StreamContentReader


class AdapterTests(TestCase):
	def application(self):
		class Hello(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(self, request):
				return Response(
					body=b'hello',
					format='text/plain',
				)

		app = Application()
		app.add(Hello)
		return app

	def test_gunicorn_adapter_wsgi_response(self):
		adapter = GunicornAdapter(self.application())
		response = {}

		def start_response(status, headers):
			response['status'] = status
			response['headers'] = dict(headers)

		body = b''.join(adapter({
			'REQUEST_METHOD': 'GET',
			'PATH_INFO': '/',
			'SERVER_PROTOCOL': 'HTTP/1.1',
			'REMOTE_ADDR': '127.0.0.1',
			'REMOTE_PORT': '12345',
			'wsgi.input': BytesIO(),
			'CONTENT_LENGTH': '',
		}, start_response))
		self.assertEqual(response['status'], '200 OK')
		self.assertEqual(response['headers']['Content-Type'], 'text/plain')
		self.assertEqual(body, b'hello')
		adapter.stop()

	async def asgi_request(
		self,
		adapter,
		method='GET',
		messages=None,
		headers=(),
	):
		messages = list(messages or [{
			'type': 'http.request',
			'body': b'',
			'more_body': False,
		}])
		responses = []

		async def receive():
			return messages.pop(0)

		async def send(message):
			responses.append(message)

		await adapter({
			'type': 'http',
			'method': method,
			'path': '/',
			'query_string': b'',
			'headers': headers,
			'http_version': '1.1',
			'client': ('127.0.0.1', 12345),
		}, receive, send)
		return responses

	def test_uvicorn_adapter_asgi_response(self):
		adapter = UvicornAdapter(self.application())
		responses = run(self.asgi_request(adapter))
		self.assertEqual(responses[0]['type'], 'http.response.start')
		self.assertEqual(responses[0]['status'], 200)
		self.assertIn((b'content-type', b'text/plain'), responses[0]['headers'])
		self.assertEqual(responses[1]['body'], b'hello')
		self.assertTrue(responses[1]['more_body'])
		self.assertEqual(responses[2]['body'], b'')
		self.assertFalse(responses[2]['more_body'])
		adapter.stop()

	def test_uvicorn_adapter_streams_chunked_request_body(self):
		class Upload(
			RequestRunner,
			method='PUT',
			url='/',
			body=Body(StreamContentReader()),
		):
			def run(self, request):
				return Response(body=request.body.read())

		app = Application()
		app.add(Upload)
		adapter = UvicornAdapter(app)
		responses = run(self.asgi_request(
			adapter,
			method='PUT',
			messages=[{
				'type': 'http.request',
				'body': b'abc',
				'more_body': True,
			}, {
				'type': 'http.request',
				'body': b'def',
				'more_body': False,
			}],
			headers=[(b'content-type', b'application/octet-stream')],
		))
		self.assertEqual(responses[1]['body'], b'abcdef')
		adapter.stop()

	def test_adapters_strip_internal_chunk_framing(self):
		class Stream(
			RequestRunner,
			method='GET',
			url='/',
		):
			def run(self, request):
				request.writer.begin(Response(), chunked=True)
				request.writer.write(b'hello')
				request.writer.end()

		app = Application()
		app.add(Stream)
		wsgi = GunicornAdapter(app)
		response = {}

		def start_response(status, headers):
			response['status'] = status

		body = b''.join(wsgi({
			'REQUEST_METHOD': 'GET',
			'PATH_INFO': '/',
			'SERVER_PROTOCOL': 'HTTP/1.1',
			'wsgi.input': BytesIO(),
			'CONTENT_LENGTH': '',
		}, start_response))
		self.assertEqual(response['status'], '200 OK')
		self.assertEqual(body, b'hello')
		wsgi.stop()

		uvicorn = UvicornAdapter(app)
		responses = run(self.asgi_request(uvicorn))
		self.assertEqual(responses[1]['body'], b'hello')
		self.assertEqual(responses[2]['body'], b'')
		uvicorn.stop()
