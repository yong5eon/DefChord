from ast import parse
from pathlib import Path
from subprocess import run
from sys import executable
from unittest import TestCase


class IndependenceTests(TestCase):
	def test_import_and_execution_without_site_packages(self):
		source = Path(__file__).resolve().parent.parent / 'src'
		script = '''
from importlib.abc import MetaPathFinder
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

class RejectExternal(MetaPathFinder):
	def find_spec(self, fullname, path=None, target=None):
		if fullname.split('.')[0] in ('DefStream', 'Liquirizia', 'swagger_ui', 'gunicorn', 'gevent'):
			raise AssertionError('external dependency: ' + fullname)
		return None

sys.meta_path.insert(0, RejectExternal())
source = Path(sys.argv[1])
spec = spec_from_file_location('DefEssential', source / '__init__.py')
module = module_from_spec(spec)
sys.modules['DefEssential'] = module
spec.loader.exec_module(module)
from DefEssential import Application, Request, RequestRunner, Response, serve
from DefEssential.Readers import StreamContentReader
from DefEssential.Writers import ChunkedStreamWriter, ServerSentEventsWriter
from DefEssential.Credentials import OAuth2AuthorizationCode
from DefEssential.Responses import ResponseFile, ResponseJSON, ResponseText
from DefEssential.Utils.FileSystemObject.Implements.FileSystem import Configuration, Connection
from DefEssential.Extensions import Metrics, Status, Specifications, Swagger, Ping

class Sample(RequestRunner, method='GET', url='/'):
	def run(self, request):
		return Response(body=b'OK')

app = Application()
app.register(Sample)
assert app(Request('127.0.0.1', 1, 'GET', '/')).body == b'OK'
extended = Application(exts=(Metrics('/metrics'), Status('/status', metrics_uri='/metrics'), Specifications('/spec'), Swagger('/swagger', spec_uri='/spec'), Ping('/ping')))
extended.start()
try:
	assert extended(Request('127.0.0.1', 1, 'GET', '/swagger')).status == 200
finally:
	extended.stop()
with serve('127.0.0.1', 0, app) as server:
	assert server.server_address[1] > 0
'''
		result = run(
			[
				executable,
				'-I',
				'-S',
				'-c',
				script,
				str(source),
			],
			capture_output=True,
			text=True,
			timeout=10,
		)
		self.assertEqual(
			result.returncode,
			0,
			result.stdout + result.stderr,
		)
		return

	def test_new_core_uses_python_39_syntax(self):
		root = Path(__file__).resolve().parent.parent / 'src'
		files = list(root.glob('*.py'))
		for directory in (
			'Readers',
			'Runners',
			'Writers',
			'Responses',
			'Extensions',
		):
			files.extend((root / directory).rglob('*.py'))
		files.append(root / 'Utils' / 'Loader.py')
		files.extend((root / 'Utils' / 'FileSystemObject').rglob('*.py'))
		files.extend((root.parent / 'samples').rglob('*.py'))
		for file in files:
			with self.subTest(file=file):
				parse(
					file.read_text(encoding='utf-8'),
					filename=str(file),
					feature_version=(3, 9),
				)
		return
