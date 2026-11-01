from http.client import HTTPConnection
from threading import Event
from unittest import TestCase

from DefChord import (
	Application,
	RequestRunner,
	Response,
)
from DefChord.IO.Writers import ServerSentEvents
from test_server import running


class SSETests(TestCase):
	def test_event_encoding(self):
		event = ServerSentEvents(
			data='첫 줄\r\n\r\n끝',
			event='sample',
			id='42',
			retry=1000,
		)
		self.assertEqual(
			event.encode(),
			'event: sample\nid: 42\nretry: 1000\ndata: 첫 줄\ndata: \ndata: 끝\n\n'.encode(),
		)
		return

	def test_invalid_fields(self):
		for event in (
			ServerSentEvents(event='a\nb'),
			ServerSentEvents(id='\x00'),
			ServerSentEvents(retry=-1),
		):
			with self.assertRaises(ValueError):
				event.encode()
		return

	def test_multiple_open_streams_do_not_block_normal_request_and_close(self):
		release = Event()
		closed = [Event() for _ in range(3)]

		def events(index):
			try:
				yield ServerSentEvents(data='first').encode()
				if not release.wait(3):
					raise TimeoutError('테스트 SSE 종료 신호가 없습니다')
				yield ServerSentEvents(data='last').encode()
			finally:
				closed[index].set()

		class Events(
			RequestRunner,
			method='GET',
			url='/events/:id',
		):
			def run(
				self,
				request,
			):
				return Response(
					body=events(int(request.parameters['id'])),
					format='text/event-stream',
					charset='utf-8',
				)

		class Normal(
			RequestRunner,
			method='GET',
			url='/normal',
		):
			def run(
				self,
				request,
			):
				return Response(body=b'ok')

		app = Application()
		app.add(Events)
		app.add(Normal)
		with running(app) as address:
			streams = [HTTPConnection(*address, timeout=3) for _ in closed]
			responses = []
			normal = HTTPConnection(
				*address,
				timeout=3,
			)
			try:
				for index, stream in enumerate(streams):
					stream.request('GET', '/events/' + str(index))
					response = stream.getresponse()
					responses.append(response)
					self.assertEqual(
						response.getheader('Content-Type'),
						'text/event-stream; charset=utf-8',
					)
					self.assertEqual(response.fp.readline(), b'data: first\n')
				self.assertFalse(any(event.is_set() for event in closed))
				normal.request(
					'GET',
					'/normal',
				)
				self.assertEqual(
					normal.getresponse().read(),
					b'ok',
				)
				self.assertFalse(any(event.is_set() for event in closed))
				release.set()
				for response in responses:
					self.assertEqual(
						response.read(),
						b'\ndata: last\n\n',
					)
				for event in closed:
					self.assertTrue(event.wait(1))
			finally:
				release.set()
				for stream in streams:
					stream.close()
				normal.close()
		return

	def test_stream_error_closes_without_second_response(self):
		closed = Event()

		def events():
			try:
				yield b'data: first\n\n'
				raise RuntimeError('전송 중 오류')
			finally:
				closed.set()

		class Events(
			RequestRunner,
			method='GET',
			url='/events',
		):
			def run(
				self,
				request,
			):
				return Response(
					body=events(),
					format='text/event-stream',
				)

		app = Application()
		app.add(Events)
		with self.assertLogs(
			'DefChord.Server',
			level='ERROR',
		) as logged:
			with running(app) as address:
				connection = HTTPConnection(
					*address,
					timeout=3,
				)
				try:
					connection.request(
						'GET',
						'/events',
					)
					response = connection.getresponse()
					self.assertEqual(
						response.status,
						200,
					)
					self.assertEqual(
						response.read(),
						b'data: first\n\n',
					)
					self.assertTrue(closed.wait(1))
				finally:
					connection.close()
		self.assertIn(
			'전송 중 오류',
			'\n'.join(logged.output),
		)
		return
