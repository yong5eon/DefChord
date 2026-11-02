from ast import (
	Assign,
	AsyncFunctionDef,
	ClassDef,
	FunctionDef,
	Import,
	ImportFrom,
	Name,
	Tuple,
	literal_eval,
	parse,
)
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from unittest import (
	TestCase,
	skipUnless,
)


class ExportTests(TestCase):
	"""Validate every module's public export format and actual wildcard imports."""

	def test_all_modules_declare_exports_before_definitions(self):
		source = Path(__file__).resolve().parent.parent / 'src'
		for file in sorted(source.rglob('*.py')):
			with self.subTest(file=file.relative_to(source)):
				tree = parse(
					file.read_text(encoding='utf-8'),
					filename=str(file),
					feature_version=(3, 9),
				)
				declarations = [
					node for node in tree.body
					if isinstance(node, Assign)
					and any(
						isinstance(target, Name) and target.id == '__all__'
						for target in node.targets
					)
				]
				self.assertEqual(len(declarations), 1)
				declaration = declarations[0]
				self.assertIsInstance(declaration.value, Tuple)
				exports = literal_eval(declaration.value)
				self.assertTrue(all(
					isinstance(name, str) and name.isidentifier()
					for name in exports
				))
				self.assertEqual(len(exports), len(set(exports)))
				if exports:
					self.assertGreater(declaration.end_lineno, declaration.lineno)
				for node in tree.body:
					if isinstance(node, (
						Import,
						ImportFrom,
					)):
						self.assertLess(node.end_lineno, declaration.lineno)
					elif isinstance(node, (
						ClassDef,
						FunctionDef,
						AsyncFunctionDef,
					)):
						self.assertGreater(node.lineno, declaration.end_lineno)
		return

	def assert_module_exports(self, name):
		module = import_module(name)
		namespace = {}
		exec('from ' + name + ' import *', namespace)
		self.assertEqual(
			set(namespace) - {'__builtins__'},
			set(module.__all__),
		)
		for symbol in module.__all__:
			self.assertIs(namespace[symbol], getattr(module, symbol))
		return

	def test_module_exports_resolve_without_leaking_imports(self):
		source = Path(__file__).resolve().parent.parent / 'src'
		for file in sorted(source.rglob('*.py')):
			parts = file.relative_to(source).with_suffix('').parts
			if parts[-1] == '__init__':
				parts = parts[:-1]
			name = '.'.join(('DefChord',) + parts)
			if name == 'DefChord.Adapter.Implements.Uvicorn.HTTP':
				continue
			with self.subTest(module=name):
				self.assert_module_exports(name)
		return

	@skipUnless(find_spec('a2wsgi') is not None, 'a2wsgi 필요')
	def test_optional_uvicorn_http_exports(self):
		self.assert_module_exports('DefChord.Adapter.Implements.Uvicorn.HTTP')
		return
