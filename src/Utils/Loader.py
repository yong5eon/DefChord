from hashlib import sha256
from importlib import import_module
from importlib.util import (
	module_from_spec,
	spec_from_file_location,
)
from pathlib import Path
from pkgutil import walk_packages
from sys import modules
from types import ModuleType
from typing import (
	List,
	Optional,
)


class Loader:
	"""모듈 또는 파일·디렉터리를 재실행 없이 로드한다."""

	def path(
		self,
		path: str,
	) -> ModuleType:
		source = Path(path).resolve(strict=True)
		name = 'defstar_loaded_' + sha256(str(source).encode('utf-8')).hexdigest()
		if name in modules:
			return modules[name]
		spec = spec_from_file_location(
			name,
			source,
		)
		if spec is None or spec.loader is None:
			raise ImportError('Python 모듈을 로드할 수 없습니다: ' + str(source))
		module = module_from_spec(spec)
		modules[name] = module
		try:
			spec.loader.exec_module(module)
		except BaseException:
			del modules[name]
			raise
		return module

	def mod(
		self,
		mod: str,
	) -> List[ModuleType]:
		module = import_module(mod)
		loaded = [module]
		if hasattr(module, '__path__'):
			for entry in walk_packages(
				module.__path__,
				module.__name__ + '.',
			):
				loaded.append(import_module(entry.name))
		return loaded

	def __call__(
		self,
		mod: Optional[str] = None,
		path: Optional[str] = None,
	) -> List[ModuleType]:
		if mod is None and path is None:
			raise ValueError('mod 또는 path가 필요합니다')
		loaded = self.mod(mod) if mod is not None else []
		if path is not None:
			source = Path(path).resolve(strict=True)
			if source.is_file():
				loaded.append(self.path(str(source)))
			elif (source / '__init__.py').is_file():
				root = self.path(str(source / '__init__.py'))
				loaded.extend(self.mod(root.__name__))
			else:
				for file in sorted(source.rglob('*.py')):
					if file.name == '__init__.py':
						continue
					loaded.append(self.path(str(file)))
		return loaded
