from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from DefEssential import (
	Application,
	Request,
)


class LoadingTests(TestCase):
	def test_directory_and_relative_package_imports(self):
		with TemporaryDirectory() as temporary:
			path = Path(temporary)
			(path / '__init__.py').write_text(
				'from .handlers import Sample\n',
				encoding='utf-8',
			)
			(path / 'handlers.py').write_text(
				'from DefEssential import RequestRunner, Response\n'
				'class Sample(RequestRunner, method="GET", url="/sample"):\n'
				'\tdef run(self, request):\n'
				'\t\treturn Response(body=b"loaded")\n',
				encoding='utf-8',
			)
			first = Application()
			second = Application()
			first.load(path=temporary)
			second.load(path=temporary)
			self.assertIs(
				first.router.routes[0].object,
				second.router.routes[0].object,
			)
			self.assertEqual(
				second(Request(
					'127.0.0.1',
					1,
					'GET',
					'/sample',
				)).body,
				b'loaded',
			)
		return

	def test_missing_path_and_import_error_are_not_hidden(self):
		app = Application()
		with self.assertRaises(FileNotFoundError):
			app.load(path=str(Path(__file__).parent / 'missing.py'))
		with TemporaryDirectory() as temporary:
			path = Path(temporary) / 'broken.py'
			path.write_text(
				'raise RuntimeError("broken module")\n',
				encoding='utf-8',
			)
			for _ in range(2):
				with self.assertRaisesRegex(
					RuntimeError,
					'broken module',
				):
					app.load(path=str(path))
		return
