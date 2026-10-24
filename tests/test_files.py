from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from http.client import HTTPConnection

from DefEssential import (
	Application,
	ClientError,
	ExtensionRequest,
	ExtensionRequestResponse,
	Response,
	ResponseWriter,
)
from DefEssential.Responses import ResponseFile
from DefEssential.Responses.ResponseFile import FileBody
from DefEssential.Extensions import (
	File,
	FileSystem,
)
from DefEssential.Utils.FileSystemObject.Implements.FileSystem import (
	Configuration,
	Connection,
)

from test_features import request
from test_server import running


class FileTests(TestCase):
	def test_filesystem_lifecycle_dynamic_files_and_http_head(self):
		with TemporaryDirectory() as directory:
			root = Path(directory)
			file = root / 'sample.txt'
			file.write_bytes(b'content')
			connection = Connection(Configuration(directory))
			app = Application(exts=(
				File('/fixed', file),
				FileSystem('/files', connection),
			))
			with patch.object(connection, 'connect', wraps=connection.connect) as connect:
				with patch.object(connection, 'close', wraps=connection.close) as close:
					with running(app) as address:
						connect.assert_called_once_with()
						(root / 'new.txt').write_bytes(b'new')
						client = HTTPConnection(*address, timeout=3)
						try:
							for path in (
								'/fixed',
								'/files/sample.txt',
							):
								client.request('HEAD', path)
								response = client.getresponse()
								self.assertEqual(response.status, 200)
								self.assertEqual(response.getheader('Content-Type'), 'text/plain')
								self.assertEqual(response.read(), b'')
							client.request('GET', '/files/new.txt')
							response = client.getresponse()
							self.assertEqual(response.status, 200)
							self.assertEqual(response.read(), b'new')
						finally:
							client.close()
					close.assert_called_once_with()
			self.assertFalse(app.running)
		return

	def test_file_extensions_ownership_and_routes(self):
		with TemporaryDirectory() as directory:
			fso = Connection(Configuration(directory))
			file = File('/file', Path(directory) / 'sample.txt')
			files = FileSystem('/files', fso)
			app = Application(exts=(file, files))
			self.assertEqual(app.router.routes, [])
			app.start()
			self.addCleanup(app.stop)
			self.assertEqual(set(app.router.matches('/file')), {'GET', 'HEAD'})
			self.assertEqual(set(app.router.matches('/files/sample.txt')), {'GET', 'HEAD'})
			self.assertEqual(app.exts, (file, files))
			with self.assertRaises(ValueError):
				Application(exts=(file,))
			with self.assertRaises(ValueError):
				Application(exts=(files,))
		return

	def test_local_connection_metadata_and_file_context(self):
		with TemporaryDirectory() as directory:
			path = Path(directory) / 'sample.txt'
			path.write_text('본문', encoding='utf-8')
			fso = Connection(Configuration(directory))
			fso.connect()
			self.assertTrue(fso.exist('sample.txt'))
			self.assertEqual(fso.type('sample.txt')[0], 'text/plain')
			self.assertEqual(fso.size('sample.txt'), len('본문'.encode()))
			self.assertIsInstance(fso.timestamp('sample.txt'), float)
			self.assertTrue(fso.modified('sample.txt').endswith('GMT'))
			self.assertEqual(len(fso.etag('sample.txt')), 64)
			self.assertEqual(fso.files(''), ['sample.txt'])
			with fso.open('sample.txt', encoding='utf-8') as file:
				self.assertEqual(file.read(0), '')
				self.assertEqual(file.read(), '본문')
			self.assertIsNone(file.fo)
			fso.close()
		return

	def test_static_tree_prefix_filters_and_errors(self):
		with TemporaryDirectory() as directory:
			root = Path(directory)
			(root / 'sample.txt').write_bytes(b'content')
			(root / 'nested').mkdir()
			(root / 'nested' / 'file.bin').write_bytes(b'\x00\xff')
			fso = Connection(Configuration(directory))

			class Rewrite(ExtensionRequest):
				def __call__(self, req):
					req.params['path'] += '.txt'
					return req

			app = Application(exts=(
				File('/fixed', root / 'sample.txt'),
				FileSystem('/tree', Connection(Configuration(directory))),
				FileSystem('/dynamic', fso, on_request=Rewrite()),
			))
			app.start()
			self.addCleanup(app.stop)
			for url, expected in (
				('/fixed', b'content'),
				('/tree/sample.txt', b'content'),
				('/tree/nested/file.bin', b'\x00\xff'),
				('/dynamic/sample', b'content'),
			):
				response = app(request(url))
				assert isinstance(response, Response)
				assert isinstance(response.body, FileBody)
				try:
					self.assertEqual(b''.join(response.body), expected)
				finally:
					response.close()
				self.assertTrue(response.body.closed)
			for url, status in (
				('/dynamic/missing', 404),
				('/dynamic/../outside', 403),
				('/dynamic/%2e%2e%2foutside', 403),
				('/dynamic/C%3A%5Coutside', 403),
				('/dynamic/%00', 403),
				('/dynamical/sample', 404),
			):
				with self.assertRaises(ClientError) as caught:
					app(request(url))
				self.assertEqual(caught.exception.status, status)
			with self.assertRaises(ClientError):
				Application()(request('/fixed'))
		return

	def test_file_closed_on_head_filter_replacement_and_error(self):
		with TemporaryDirectory() as directory:
			path = Path(directory) / 'file.txt'
			path.write_bytes(b'content')
			response = ResponseFile(path)
			assert isinstance(response.body, FileBody)
			output = BytesIO()
			writer = ResponseWriter(
				lambda response, chunked: None,
				output,
				method='HEAD',
			)
			try:
				writer.response(response)
			finally:
				response.close()
			self.assertTrue(response.body.closed)
			self.assertEqual(output.getvalue(), b'')
			captured = []

			class FileResponseFilter(ExtensionRequestResponse):
				def __init__(self, action):
					self.action = action
					return

				def __call__(self, req, response):
					captured.append(response.body)
					if self.action == 'replace':
						return Response(body=b'replaced')
					if self.action == 'fail':
						raise ValueError('응답 필터 실패')
					response.body = b'mutated'
					return response

			app = Application(exts=(
				File('/replace', path, on_request_response=FileResponseFilter('replace')),
				File('/fail', path, on_request_response=FileResponseFilter('fail')),
				File('/mutate', path, on_request_response=FileResponseFilter('mutate')),
			))
			app.start()
			self.addCleanup(app.stop)
			replacement = app(request('/replace'))
			assert isinstance(replacement, Response)
			self.assertEqual(replacement.body, b'replaced')
			with self.assertRaises(ValueError):
				app(request('/fail'))
			mutated = app(request('/mutate'))
			assert isinstance(mutated, Response)
			self.assertEqual(mutated.body, b'mutated')
			self.assertTrue(all(body.closed for body in captured))
		return

	def test_bounded_file_reading_encoding_and_nested_mount_priority(self):
		with TemporaryDirectory() as directory:
			root = Path(directory)
			content = b'x' * 200000
			(root / 'large.bin').write_bytes(content)
			(root / 'file.txt.gz').write_bytes(b'compressed')
			app = Application(exts=(
				FileSystem('/files', Connection(Configuration(directory))),
				FileSystem('/files/nested', Connection(Configuration(directory))),
				File('/files/fixed', root / 'large.bin'),
			))
			app.start()
			self.addCleanup(app.stop)
			for url in (
				'/files/large.bin',
				'/files/nested/large.bin',
				'/files/fixed',
			):
				response = app(request(url))
				assert isinstance(response, Response)
				assert isinstance(response.body, FileBody)
				try:
					parts = list(response.body)
					self.assertEqual([len(part) for part in parts], [65536, 65536, 65536, 3392])
					self.assertEqual(b''.join(parts), content)
				finally:
					response.close()
			for url in (
				'/files/file.txt.gz',
				'/files/nested/file.txt.gz',
			):
				response = app(request(url))
				assert isinstance(response, Response)
				try:
					self.assertEqual(response.header('Content-Type'), 'text/plain')
					self.assertEqual(response.header('Content-Encoding'), 'gzip')
				finally:
					response.close()
			response = ResponseFile(root / 'file.txt.gz')
			try:
				self.assertEqual(response.header('Content-Encoding'), 'gzip')
			finally:
				response.close()
		return
