from base64 import b64encode
from io import BytesIO
from socket import create_connection
from struct import (
	pack,
	unpack,
)
from threading import Event
from unittest import TestCase

from DefChord import (
	Application,
	ApplicationRequestError,
	ApplicationRequestResponse,
	Request,
	RequestRunner,
	Response,
	RequestRunnerRequestResponse,
	ResponseWriter,
)
from DefChord.IO.RequestReader import (
	ClientDisconnected,
	RequestReader,
)
from DefChord.IO.WebSocket import (
	WebSocket,
	WebSocketError,
	WebSocketFrame,
	WebSocketFrameReader,
	WebSocketHandshake,
)

from test_server import running


KEY = 'dGhlIHNhbXBsZSBub25jZQ=='
MASK = b'\x01\x02\x03\x04'


def client_frame(
	opcode,
	payload=b'',
	final=True,
	masked=True,
):
	"""Build a masked frame as sent by a client."""
	first = (0x80 if final else 0) | opcode
	flag = 0x80 if masked else 0
	size = len(payload)
	if size < 126:
		header = pack('!BB', first, flag | size)
	elif size < 65536:
		header = pack('!BBH', first, flag | 126, size)
	else:
		header = pack('!BBQ', first, flag | 127, size)
	if not masked:
		return header + payload
	return header + MASK + bytes(byte ^ MASK[index % 4] for index, byte in enumerate(payload))


def handshake_request(
	headers=None,
	path='/ws',
):
	values = {
		'Host': 'localhost',
		'Upgrade': 'websocket',
		'Connection': 'keep-alive, Upgrade',
		'Sec-WebSocket-Key': KEY,
		'Sec-WebSocket-Version': '13',
	}
	values.update(headers or {})
	lines = ['GET ' + path + ' HTTP/1.1']
	lines.extend(key + ': ' + value for key, value in values.items() if value is not None)
	return ('\r\n'.join(lines) + '\r\n\r\n').encode('ascii')


class Client:
	"""A raw WebSocket client for tests."""

	def __init__(
		self,
		address,
		headers=None,
		path='/ws',
	):
		self.socket = create_connection(
			address,
			timeout=3,
		)
		self.file = self.socket.makefile('rb')
		self.socket.sendall(handshake_request(
			headers,
			path,
		))
		status = self.file.readline().decode('ascii')
		self.status = int(status.split()[1])
		self.headers = {}
		while True:
			line = self.file.readline().decode('ascii').rstrip('\r\n')
			if not line:
				break
			key, _, value = line.partition(':')
			self.headers[key.strip().lower()] = value.strip()
		return

	def body(self):
		return self.file.read(int(self.headers['content-length']))

	def send(
		self,
		*frames,
	):
		self.socket.sendall(b''.join(frames))
		return

	def receive(self):
		first, second = self.file.read(2)
		self.assert_unmasked(second)
		size = second & 0x7F
		if size == 126:
			size = unpack('!H', self.file.read(2))[0]
		elif size == 127:
			size = unpack('!Q', self.file.read(8))[0]
		return (
			first & 0x0F,
			bool(first & 0x80),
			self.file.read(size),
		)

	def assert_unmasked(
		self,
		second,
	):
		if second & 0x80:
			raise AssertionError('Server frames must not be masked')
		return

	def close(self):
		self.file.close()
		self.socket.close()
		return


def echo_application(
	limit=16,
	completed=None,
):
	class Echo(
		RequestRunner,
		method='GET',
		url='/ws',
	):
		def run(
			self,
			request,
		):
			socket = WebSocket(
				request,
				limit=limit,
			)
			socket.accept('chat' if 'chat' in socket.protocols else None)
			while True:
				message = socket.receive()
				if message is None:
					break
				socket.send(message)
			return

	class RequestResponse(ApplicationRequestResponse):
		"""Observe the WebSocket handler return rather than transmission completion."""

		def __call__(
			self,
			request,
			response,
		):
			if completed is not None:
				completed.append(response)
			return response

	app = Application(on_request_response=RequestResponse())
	app.add(Echo)
	return app


class WebSocketUnitTests(TestCase):
	def request(
		self,
		headers=None,
		method='GET',
		version='HTTP/1.1',
		data=b'',
	):
		values = {
			'Upgrade': 'websocket',
			'Connection': 'Upgrade',
			'Sec-WebSocket-Key': KEY,
			'Sec-WebSocket-Version': '13',
		}
		values.update(headers or {})
		self.output = BytesIO()
		self.sent = []
		return Request(
			'127.0.0.1',
			1,
			method,
			'/ws',
			headers={key: value for key, value in values.items() if value is not None},
			reader=RequestReader(BytesIO(data)),
			writer=ResponseWriter(
				lambda response, chunked: self.sent.append(response),
				self.output,
				method=method,
				version=version,
			),
		)

	def test_handshake_accept_key_and_subprotocol(self):
		request = self.request({'Sec-WebSocket-Protocol': 'chat, superchat'})
		handshake = WebSocketHandshake(request)
		self.assertEqual(handshake.protocols, ['chat', 'superchat'])
		response = handshake.response('superchat')
		self.assertEqual(response.status, 101)
		self.assertEqual(response.header('Sec-WebSocket-Accept'), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
		self.assertEqual(response.header('Sec-WebSocket-Protocol'), 'superchat')
		self.assertEqual(response.header('Upgrade'), 'websocket')
		self.assertEqual(response.header('Connection'), 'Upgrade')
		with self.assertRaises(ValueError):
			handshake.response('unknown')
		return

	def test_handshake_rejections(self):
		for headers, method, version, status, header in (
			({}, 'POST', 'HTTP/1.1', 400, None),
			({}, 'GET', 'HTTP/1.0', 400, None),
			({'Upgrade': None}, 'GET', 'HTTP/1.1', 426, ('Upgrade', 'websocket')),
			({'Connection': 'keep-alive'}, 'GET', 'HTTP/1.1', 400, None),
			({'Sec-WebSocket-Version': '8'}, 'GET', 'HTTP/1.1', 426, ('Sec-WebSocket-Version', '13')),
			({'Sec-WebSocket-Key': None}, 'GET', 'HTTP/1.1', 400, None),
			({'Sec-WebSocket-Key': 'short'}, 'GET', 'HTTP/1.1', 400, None),
			({'Sec-WebSocket-Key': b64encode(b'x' * 15).decode('ascii')}, 'GET', 'HTTP/1.1', 400, None),
		):
			with self.subTest(headers=headers, method=method, version=version):
				with self.assertRaises(Exception) as caught:
					WebSocketHandshake(self.request(
						headers,
						method=method,
						version=version,
					)).validate()
				self.assertEqual(caught.exception.status, status)
				if header is not None:
					self.assertEqual(caught.exception.headers[header[0]], header[1])
		return

	def test_frame_encoding_lengths(self):
		for size, header in (
			(0, b'\x82\x00'),
			(125, b'\x82\x7d'),
			(126, b'\x82\x7e\x00\x7e'),
			(65536, b'\x82\x7f' + pack('!Q', 65536)),
		):
			with self.subTest(size=size):
				data = WebSocketFrame(WebSocketFrame.BINARY, b'a' * size).encode()
				self.assertEqual(data[:len(header)], header)
				self.assertEqual(len(data), len(header) + size)
		self.assertEqual(WebSocketFrame(WebSocketFrame.TEXT, b'a', final=False).encode()[0], 0x01)
		for opcode, payload, final in (
			(0x3, b'', True),
			(WebSocketFrame.PING, b'a' * 126, True),
			(WebSocketFrame.CLOSE, b'', False),
		):
			with self.assertRaises(ValueError):
				WebSocketFrame(opcode, payload, final)
		return

	def test_frame_reader_unmasks_and_rejects_protocol_violations(self):
		frame = WebSocketFrameReader(
			RequestReader(BytesIO(client_frame(WebSocketFrame.TEXT, b'hello'))),
			16,
		).read()
		self.assertEqual((frame.opcode, frame.final, frame.payload), (WebSocketFrame.TEXT, True, b'hello'))
		frame = WebSocketFrameReader(
			RequestReader(BytesIO(client_frame(WebSocketFrame.BINARY, b'x' * 70000))),
			70000,
		).read()
		self.assertEqual(frame.payload, b'x' * 70000)
		for data, code in (
			(client_frame(WebSocketFrame.TEXT, b'a', masked=False), 1002),
			(bytes([0xC1]) + client_frame(WebSocketFrame.TEXT, b'a')[1:], 1002),
			(client_frame(0x3, b'a'), 1002),
			(client_frame(WebSocketFrame.PING, b'a', final=False), 1002),
			(client_frame(WebSocketFrame.BINARY, b'a' * 17), 1009),
			(b'\x82\xff' + pack('!Q', 1 << 63), 1002),
		):
			with self.subTest(data=data[:2]):
				with self.assertRaises(WebSocketError) as caught:
					WebSocketFrameReader(
						RequestReader(BytesIO(data)),
						16,
					).read()
				self.assertEqual(caught.exception.code, code)
		with self.assertRaises(ClientDisconnected):
			WebSocketFrameReader(
				RequestReader(BytesIO(b'\x81')),
				16,
			).read()
		return

	def test_session_requires_accept_and_positive_limit(self):
		with self.assertRaises(ValueError):
			WebSocket(self.request(), limit=0)
		socket = WebSocket(self.request(), limit=16)
		with self.assertRaises(RuntimeError):
			socket.send('a')
		with self.assertRaises(RuntimeError):
			socket.receive()
		socket.accept()
		self.assertEqual(self.sent[0].status, 101)
		with self.assertRaises(RuntimeError):
			socket.accept()
		with self.assertRaises(TypeError):
			socket.send(1)
		with self.assertRaises(ValueError):
			socket.close(1005)
		with self.assertRaises(ValueError):
			socket.close(1000, 'a' * 124)
		return

	def test_upgrade_rejects_non_101_and_filter_status_changes(self):
		writer = ResponseWriter(
			lambda response, chunked: None,
			BytesIO(),
		)
		with self.assertRaises(ValueError):
			writer.upgrade(Response(status=200))
		writer.on_request_response = lambda response: Response(status=200)
		with self.assertRaises(ValueError):
			writer.upgrade(Response(status=101))
		self.assertFalse(writer.started)
		return


class WebSocketServerTests(TestCase):
	def test_echo_fragments_ping_and_close_handshake(self):
		completed = []
		with running(echo_application(completed=completed)) as address:
			client = Client(
				address,
				{'Sec-WebSocket-Protocol': 'chat'},
			)
			try:
				self.assertEqual(client.status, 101)
				self.assertEqual(client.headers['upgrade'], 'websocket')
				self.assertEqual(client.headers['connection'], 'Upgrade')
				self.assertEqual(client.headers['sec-websocket-accept'], 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
				self.assertEqual(client.headers['sec-websocket-protocol'], 'chat')
				self.assertNotIn('content-length', client.headers)
				client.send(client_frame(WebSocketFrame.TEXT, '안녕'.encode('utf-8')))
				self.assertEqual(client.receive(), (WebSocketFrame.TEXT, True, '안녕'.encode('utf-8')))
				client.send(
					client_frame(WebSocketFrame.BINARY, b'ab', final=False),
					client_frame(WebSocketFrame.PING, b'p'),
					client_frame(WebSocketFrame.CONTINUATION, b'cd'),
				)
				self.assertEqual(client.receive(), (WebSocketFrame.PONG, True, b'p'))
				self.assertEqual(client.receive(), (WebSocketFrame.BINARY, True, b'abcd'))
				client.send(client_frame(WebSocketFrame.CLOSE, pack('!H', 1000) + b'bye'))
				self.assertEqual(client.receive(), (WebSocketFrame.CLOSE, True, pack('!H', 1000)))
				self.assertEqual(client.file.read(), b'')
			finally:
				client.close()
		self.assertEqual(completed, [None])
		return

	def test_protocol_errors_send_close_codes(self):
		for frames, code in (
			((client_frame(WebSocketFrame.TEXT, b'a', masked=False),), 1002),
			((client_frame(WebSocketFrame.TEXT, b'\xff'),), 1007),
			((client_frame(WebSocketFrame.BINARY, b'a' * 17),), 1009),
			((
				client_frame(WebSocketFrame.TEXT, b'a' * 10, final=False),
				client_frame(WebSocketFrame.CONTINUATION, b'a' * 10),
			), 1009),
			((client_frame(WebSocketFrame.CONTINUATION, b'a'),), 1002),
			((client_frame(WebSocketFrame.CLOSE, pack('!H', 1005)),), 1002),
		):
			with self.subTest(code=code, frames=frames[0][:2]):
				with self.assertLogs(
					'Request.WebSocket',
					level='WARNING',
				):
					with running(echo_application()) as address:
						client = Client(address)
						try:
							client.send(*frames)
							opcode, _, payload = client.receive()
							self.assertEqual(opcode, WebSocketFrame.CLOSE)
							self.assertEqual(unpack('!H', payload[:2])[0], code)
							self.assertEqual(client.file.read(), b'')
						finally:
							client.close()
		return

	def test_failed_handshake_returns_normal_error_response(self):
		with running(echo_application()) as address:
			client = Client(
				address,
				{'Sec-WebSocket-Version': '8'},
			)
			try:
				self.assertEqual(client.status, 426)
				self.assertEqual(client.headers['sec-websocket-version'], '13')
				self.assertEqual(client.headers['connection'], 'close')
				self.assertEqual(client.body(), b'Unsupported WebSocket version')
			finally:
				client.close()
		return

	def test_response_hooks_apply_to_upgrade_headers(self):
		class Tag(RequestRunnerRequestResponse):
			def __call__(
				self,
				request,
				response,
			):
				response.header('X-Filtered', 'yes')
				return response

		class Echo(
			RequestRunner,
			method='GET',
			url='/ws',
			on_request_response=Tag(),
		):
			def run(
				self,
				request,
			):
				socket = WebSocket(
					request,
					limit=16,
				)
				socket.accept()
				socket.close(4000, 'done')
				return

		app = Application()
		app.add(Echo)
		with running(app) as address:
			client = Client(address)
			try:
				self.assertEqual(client.status, 101)
				self.assertEqual(client.headers['x-filtered'], 'yes')
				self.assertNotIn('sec-websocket-protocol', client.headers)
				self.assertEqual(client.receive(), (WebSocketFrame.CLOSE, True, pack('!H', 4000) + b'done'))
				client.send(
					client_frame(WebSocketFrame.TEXT, b'ignored'),
					client_frame(WebSocketFrame.CLOSE, pack('!H', 4000)),
				)
				self.assertEqual(client.file.read(), b'')
			finally:
				client.close()
		return

	def test_client_dropping_tcp_is_logged_as_disconnect(self):
		completed = []
		observed = Event()

		class RequestError(ApplicationRequestError):
			def __call__(
				self,
				request,
				error,
			):
				completed.append(error)
				observed.set()
				return

		class Echo(
			RequestRunner,
			method='GET',
			url='/ws',
		):
			def run(
				self,
				request,
			):
				socket = WebSocket(
					request,
					limit=16,
				)
				socket.accept()
				socket.receive()
				return

		app = Application(on_request_error=RequestError())
		app.add(Echo)
		with self.assertLogs(
			'Server',
			level='INFO',
		) as logged:
			with running(app) as address:
				client = Client(address)
				client.close()
				self.assertTrue(observed.wait(3))
		self.assertIsInstance(completed[0], ClientDisconnected)
		self.assertTrue(any(
			record.levelname == 'WARNING' and 'Client disconnected' in record.getMessage() and record.exc_info is None
			for record in logged.records
		))
		return
