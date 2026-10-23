from contextlib import contextmanager
from http.client import (
	HTTPConnection,
	HTTPResponse,
)
from importlib.util import find_spec
from os import (
	environ,
	getpid,
	name,
)
from pathlib import Path
from socket import (
	create_connection,
	socket,
)
from struct import pack
from subprocess import (
	Popen,
	TimeoutExpired,
)
from sys import (
	base_prefix,
	executable,
)
from tempfile import TemporaryDirectory
from time import (
	monotonic,
	sleep,
)
from unittest import (
	TestCase,
	skipUnless,
)

from DefEssential import (
	Application,
	Body,
	Extension,
	RequestRunner,
	Response,
)
from DefEssential.IO.Readers import (
	ChunkedStreamContentReader,
	StreamContentReader,
)
from DefEssential.IO.WebSocket import WebSocket
from DefEssential.IO.Writers import (
	ChunkedStreamWriter,
	ServerSentEventsWriter,
	StreamWriter,
)

from test_websocket import (
	Client,
	client_frame,
)


def run_server(
	adapter: str,
	port: int,
	directory: str,
	worker: str,
) -> None:
	"""서로 다른 프로세스에서도 같은 핸들러로 전송 계약을 검증한다."""
	root = Path(directory)

	def record(event: str) -> None:
		with (root / 'events').open('a') as output:
			output.write(f'{getpid()}:{event}\n')
		return

	def wait_for_release(kind: str) -> None:
		deadline = monotonic() + 6
		while not (root / kind).exists():
			if monotonic() >= deadline:
				raise TimeoutError('Client did not receive the first output in time')
			sleep(0.01)
		return

	class Observation(Extension):
		def start(
			self,
			application,
		):
			record('start')
			return

		def stop(
			self,
			application,
		):
			record('stop')
			return

		def end(
			self,
			request,
			context,
			status,
			error,
		):
			record(f'end:{request.path}:{status}')
			return

		def __call__(
			self,
			application,
			request,
		):
			return Response()

	class Health(
		RequestRunner,
		method='GET',
		url='/',
	):
		def run(
			self,
			request,
		):
			return Response(body=b'OK')

	class Upload(
		RequestRunner,
		method='PUT',
		url='/in',
		body=Body(StreamContentReader()),
	):
		def run(
			self,
			request,
		):
			first = request.body.read(3)
			writer = ChunkedStreamWriter(request.writer)
			writer.begin()
			writer.chunk(first)
			writer.chunk(request.body.read())
			writer.end()
			return

	class ChunkedUpload(
		RequestRunner,
		method='PUT',
		url='/in/chunked',
		body=Body(ChunkedStreamContentReader()),
	):
		def run(
			self,
			request,
		):
			first = request.body.chunk(65536)
			writer = ChunkedStreamWriter(request.writer)
			writer.begin()
			writer.chunk(first)
			writer.chunk(request.body.read())
			writer.end()
			return

	class Output(
		RequestRunner,
		method='GET',
		url='/out/:kind',
	):
		def run(
			self,
			request,
		):
			kind = request.params['kind']
			writer = ChunkedStreamWriter(request.writer) if kind == 'chunked' else StreamWriter(request.writer)
			writer.begin()
			writer.write(b'first')
			writer.flush()
			wait_for_release(kind)
			writer.write(b'second')
			writer.end()
			return

	class Events(
		RequestRunner,
		method='GET',
		url='/sse',
	):
		def run(
			self,
			request,
		):
			writer = ServerSentEventsWriter(request.writer)
			writer.begin()
			writer.emit('first')
			wait_for_release('sse')
			writer.emit('second')
			writer.end()
			return

	class Disconnect(
		RequestRunner,
		method='GET',
		url='/disconnect',
	):
		def run(
			self,
			request,
		):
			writer = ServerSentEventsWriter(request.writer)
			writer.begin()
			while True:
				writer.emit('alive')
				sleep(0.02)

	class Echo(
		RequestRunner,
		method='GET',
		url='/ws',
	):
		def run(
			self,
			request,
		):
			connection = WebSocket(
				request,
				limit=262144,
			)
			connection.accept('chat' if 'chat' in connection.protocols else None)
			while True:
				message = connection.receive()
				if message is None:
					break
				connection.send(message)
			return

	application = Application(exts=(Observation('/observation'),))
	for handler in (
		Health,
		Upload,
		ChunkedUpload,
		Output,
		Events,
		Disconnect,
		Echo,
	):
		application.add(handler)
	if adapter == 'Python':
		from DefEssential.Adapter.Implements.Python import Server

		Server(
			'127.0.0.1',
			port,
			application,
		).run()
	elif adapter == 'Uvicorn':
		from DefEssential.Adapter.Implements.Uvicorn import Server

		Server(
			'127.0.0.1',
			port,
			application,
			log_level='warning',
		).run()
	else:
		from DefEssential.Adapter.Implements.Gunicorn import Server

		Server(
			'127.0.0.1',
			port,
			application,
			worker_class=worker,
			workers=2,
			threads=2 if worker == 'gthread' else 1,
			graceful_timeout=3,
		).run()
	return


class TransportConformanceTests(TestCase):
	@contextmanager
	def running(
		self,
		adapter,
		worker,
	):
		from DefEssential import __file__ as package_file

		script = '''
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
source, tests, adapter, port, directory, worker = sys.argv[1:]
spec = spec_from_file_location('DefEssential', Path(source) / '__init__.py')
module = module_from_spec(spec)
sys.modules['DefEssential'] = module
spec.loader.exec_module(module)
sys.path.insert(0, tests)
from test_transport_conformance import run_server
run_server(adapter, int(port), directory, worker)
'''
		with TemporaryDirectory() as directory:
			root = Path(directory)
			log = root / 'server.log'
			with socket() as listener:
				listener.bind((
					'127.0.0.1',
					0,
				))
				port = listener.getsockname()[1]
			with log.open('w') as output:
				environment = dict(environ)
				if name == 'nt':
					# venv 리다이렉터 대신 실제 인터프리터를 종료해야 로그 핸들도 함께 닫힌다.
					environment['__PYVENV_LAUNCHER__'] = executable
				process = Popen(
					[
						str(Path(base_prefix) / Path(executable).name) if name == 'nt' else executable,
						'-c',
						script,
						str(Path(package_file).parent),
						str(Path(__file__).parent),
						adapter,
						str(port),
						directory,
						worker,
					],
					stdout=output,
					stderr=output,
					env=environment,
				)
			try:
				deadline = monotonic() + 30
				while True:
					self.assertIsNone(process.poll(), log.read_text(errors='replace'))
					connection = HTTPConnection('127.0.0.1', port, timeout=0.2)
					try:
						connection.request('GET', '/')
						response = connection.getresponse()
						if response.read() == b'OK':
							break
					except OSError:
						if monotonic() >= deadline:
							raise TimeoutError(log.read_text(errors='replace'))
						sleep(0.02)
					finally:
						connection.close()
				yield (
					port,
					root,
				)
			except BaseException:
				print(log.read_text(errors='replace'))
				raise
			finally:
				if process.poll() is None:
					process.terminate()
				try:
					process.wait(timeout=10)
				except TimeoutExpired:
					process.kill()
					process.wait(timeout=5)
					raise

	def exercise(
		self,
		adapter,
		worker='',
	):
		with self.running(adapter, worker) as (port, root):
			for chunked in (
				False,
				True,
			):
				with self.subTest(feature='input', chunked=chunked):
					connection = create_connection((
						'127.0.0.1',
						port,
					), timeout=3)
					try:
						path = '/in/chunked' if chunked else '/in'
						framing = 'Transfer-Encoding: chunked' if chunked else 'Content-Length: 6'
						connection.sendall((
							f'PUT {path} HTTP/1.1\r\n'
							'Host: localhost\r\n'
							'Content-Type: application/octet-stream\r\n'
							f'{framing}\r\n\r\n'
						).encode('ascii'))
						connection.sendall(b'3\r\nabc\r\n' if chunked else b'abc')
						response = HTTPResponse(connection)
						response.begin()
						self.assertEqual(response.status, 200)
						self.assertEqual(response.read(3), b'abc', '업로드 완료 전에 첫 데이터를 반환해야 합니다')
						connection.sendall(b'3\r\ndef\r\n0\r\n\r\n' if chunked else b'def')
						self.assertEqual(response.read(), b'def')
					finally:
						connection.close()
			for kind in (
				'plain',
				'chunked',
				'sse',
			):
				with self.subTest(feature=kind):
					connection = HTTPConnection('127.0.0.1', port, timeout=3)
					try:
						connection.request('GET', '/sse' if kind == 'sse' else '/out/' + kind)
						response = connection.getresponse()
						self.assertEqual(response.status, 200)
						if kind == 'sse':
							self.assertEqual(response.getheader('Content-Type'), 'text/event-stream; charset=utf-8')
							self.assertEqual(response.readline(), b'data: first\n')
							self.assertEqual(response.readline(), b'\n')
						else:
							self.assertEqual(response.read(5), b'first')
						(root / kind).touch()
						expected = b'data: second\n\n' if kind == 'sse' else b'second'
						self.assertEqual(response.read(), expected)
					finally:
						connection.close()
			with self.subTest(feature='websocket'):
				client = Client(
					(
						'127.0.0.1',
						port,
					),
					headers={'Sec-WebSocket-Protocol': 'chat'},
				)
				try:
					self.assertEqual(client.status, 101)
					self.assertEqual(client.headers['sec-websocket-protocol'], 'chat')
					for opcode, payload in (
						(
							1,
							'메시지'.encode('utf-8'),
						),
						(
							2,
							b'\x00\xff' * 32768,
						),
					):
						client.send(client_frame(opcode, payload))
						self.assertEqual(client.receive(), (
							opcode,
							True,
							payload,
						))
					client.send(
						client_frame(1, b'frag', final=False),
						client_frame(9, b'ping'),
						client_frame(0, b'ment'),
					)
					self.assertEqual(client.receive(), (
						10,
						True,
						b'ping',
					))
					self.assertEqual(client.receive(), (
						1,
						True,
						b'fragment',
					))
					client.send(client_frame(8, pack('!H', 1000)))
					self.assertEqual(client.receive()[0], 8)
				finally:
					client.close()
			with self.subTest(feature='disconnect'):
				connection = HTTPConnection('127.0.0.1', port, timeout=3)
				connection.request('GET', '/disconnect')
				response = connection.getresponse()
				self.assertEqual(response.readline(), b'data: alive\n')
				response.close()
				connection.close()
				deadline = monotonic() + 5
				while ':end:/disconnect:' not in (root / 'events').read_text():
					if monotonic() >= deadline:
						self.fail('클라이언트 연결 종료 뒤 SSE 핸들러가 정리되지 않았습니다')
					sleep(0.02)
		return

	def test_python(self):
		self.exercise('Python')
		return

	@skipUnless(find_spec('uvicorn') and find_spec('a2wsgi'), 'Uvicorn 선택적 의존성 필요')
	def test_uvicorn(self):
		self.exercise('Uvicorn')
		return

	@skipUnless(name == 'posix' and find_spec('gunicorn'), 'Gunicorn과 POSIX 환경 필요')
	def test_gunicorn_sync(self):
		self.exercise('Gunicorn', 'sync')
		return

	@skipUnless(name == 'posix' and find_spec('gunicorn'), 'Gunicorn과 POSIX 환경 필요')
	def test_gunicorn_gthread(self):
		self.exercise('Gunicorn', 'gthread')
		return

	@skipUnless(name == 'posix' and find_spec('gunicorn') and find_spec('gevent'), 'Gunicorn과 gevent 및 POSIX 환경 필요')
	def test_gunicorn_gevent(self):
		self.exercise('Gunicorn', 'gevent')
		return
