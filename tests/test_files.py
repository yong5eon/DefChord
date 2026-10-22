from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from DefEssential import (
	Application,
	ClientError,
	Response,
	ResponseWriter,
)
from DefEssential.Responses import ResponseFile
from DefEssential.Responses.ResponseFile import FileBody
from DefEssential.Runners.RunFactory import RunFactory
from DefEssential.Runners.RunFile import RunFileFactory
from DefEssential.Runners.RunFileSystemObject import (
	RunFileSystemObjectFactory,
	FileSystemRoute,
)
from DefEssential.Utils.FileSystemObject.Implements.FileSystem import (
	Configuration,
	Connection,
)

from test_features import request


class FileTests(TestCase):
	def test_file_factories_contract_and_independent_results(self):
		with TemporaryDirectory() as directory:
			fso = Connection(Configuration(directory))
			factories = (
				RunFileFactory(Path(directory) / 'sample.txt', '/file'),
				RunFileSystemObjectFactory(fso, '/files'),
			)
			for factory in factories:
				self.assertIsInstance(factory, RunFactory)
				first = factory()
				second = factory()
				self.assertIsNot(first, second)
				if isinstance(first, FileSystemRoute):
					self.assertEqual(first.match('/files/sample.txt'), {'path': 'sample.txt'})
					self.assertIsInstance(second, FileSystemRoute)
				else:
					self.assertEqual(first.properties.method, 'GET')
					self.assertEqual(first.properties.url, '/file')
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
			app = Application()
			app.add_file(root / 'sample.txt', '/fixed')
			app.add_files(root, '/tree')
			fso = Connection(Configuration(directory))

			def rewrite(req):
				req.params['path'] += '.txt'
				return req, None

			app.add_file_system_object(fso, '/dynamic', onRequest=rewrite)
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

			def replace(req, response):
				captured.append(response.body)
				return Response(body=b'replaced')

			def fail(req, response):
				captured.append(response.body)
				raise ValueError('응답 필터 실패')

			def mutate(req, response):
				captured.append(response.body)
				response.body = b'mutated'
				return response

			app = Application()
			app.add_file(path, '/replace', onResponse=replace)
			app.add_file(path, '/fail', onResponse=fail)
			app.add_file(path, '/mutate', onResponse=mutate)
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
			app = Application()
			app.add_file_system_object(Connection(Configuration(directory)), '/files')
			app.add_file_system_object(Connection(Configuration(directory)), '/files/nested')
			app.add_file(root / 'large.bin', '/files/fixed')
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
