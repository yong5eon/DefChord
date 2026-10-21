from inspect import isabstract
from pathlib import Path
from logging import getLogger
from threading import RLock
from typing import (
	Optional,
	Sequence,
	Type,
)

from .Error import ClientError
from .RequestRunner import RequestRunner
from .Request import Request
from .Response import Response
from .Route import Route
from .Router import Router
from .Runners import RunRequest
from .Utils.Loader import Loader
from .Runners.RunOptions import RunOptions
from .Runners.RunFile import file_handler
from .Runners.RunFileSystemObject import filesystem_handler
from .Utils.FileSystemObject import Connection
from .Extension import Extension
from .Runners.RunExtension import extension_handler


class Application:
	"""등록 상태를 소유하고 요청별 처리기 인스턴스를 실행한다."""

	def __init__(
		self,
		exts: Sequence[Extension] = (),
	):
		self.router = Router()
		self.exts: dict[str, Extension] = {}
		self.running = False
		self.lifecycle_lock = RLock()
		extensions = tuple(exts)
		for extension in extensions:
			if not isinstance(extension, Extension):
				raise TypeError('exts에는 Extension 인스턴스가 필요합니다')
			if extension.application is not None:
				raise ValueError('확장 인스턴스는 다른 Application과 공유할 수 없습니다')
			if extension.path in self.exts:
				raise ValueError('중복된 확장 경로: ' + extension.path)
			self.exts[extension.path] = extension
		try:
			for extension in extensions:
				for method in extension.methods:
					self.register(extension_handler(
						self,
						extension,
						method,
					))
			for extension in extensions:
				extension.bind(self)
		except Exception:
			self.exts.clear()
			raise
		for extension in extensions:
			extension.application = self
		return

	def start(self) -> None:
		"""서버 실행 전에 확장을 선언 순서로 시작한다."""
		with self.lifecycle_lock:
			if self.running:
				raise RuntimeError('이미 실행 중인 Application입니다')
			started = []
			try:
				for extension in self.exts.values():
					extension.start(self)
					started.append(extension)
			except Exception:
				for extension in reversed(started):
					try:
						extension.stop(self)
					except Exception:
						getLogger('DefStar.Application').exception('확장 시작 실패 후 정리 오류')
				raise
			self.running = True
		return

	def stop(self) -> None:
		"""시작한 확장을 역순으로 종료하고 정리 오류를 전파한다."""
		with self.lifecycle_lock:
			if not self.running:
				return
			self.running = False
			first_error = None
			for extension in reversed(tuple(self.exts.values())):
				try:
					extension.stop(self)
				except Exception as error:
					getLogger('DefStar.Application').exception('확장 종료 오류')
					if first_error is None:
						first_error = error
			if first_error is not None:
				raise first_error
		return

	def register(
		self,
		handler: Type[RequestRunner],
	) -> None:
		if self.running:
			raise RuntimeError('실행 중에는 처리기를 등록할 수 없습니다')
		if not issubclass(
			handler,
			RequestRunner,
		) or isabstract(handler):
			raise TypeError('구체적인 RequestRunner 클래스가 필요합니다')
		properties = handler.properties
		if properties.method is None or properties.url is None:
			raise ValueError('등록할 처리기에 method와 url이 필요합니다')
		self.router.add(Route(
			properties.method,
			properties.url,
			handler,
		))
		return

	def load(
		self,
		mod: Optional[str] = None,
		path: Optional[str] = None,
	) -> None:
		"""이미 import된 모듈도 각 Application에 독립적으로 등록한다."""
		for module in Loader()(
			mod=mod,
			path=path,
		):
			for value in vars(module).values():
				if (
					isinstance(value, type)
					and issubclass(value, RequestRunner)
					and value is not RequestRunner
					and value.__module__ == module.__name__
					and not isabstract(value)
				):
					self.register(value)
		return

	def add_file(
		self,
		path,
		url: str,
		onRequest=None,
		onResponse=None,
	) -> None:
		"""고정 URL에 파일 응답을 등록한다."""
		self.register(file_handler(
			path,
			url,
			on_request=onRequest,
			on_response=onResponse,
		))
		return

	def add_files(
		self,
		path,
		prefix: str,
		onRequest=None,
		onResponse=None,
	) -> None:
		"""기존 파일 트리의 각 파일을 독립 라우트로 등록한다."""
		root = Path(path).resolve(strict=True)
		if not root.is_dir():
			raise NotADirectoryError(str(root))
		for file in sorted(root.rglob('*')):
			if file.is_file():
				file.resolve().relative_to(root)
				self.add_file(
					file,
					prefix.rstrip('/') + '/' + file.relative_to(root).as_posix(),
					onRequest=onRequest,
					onResponse=onResponse,
				)
		return

	def add_file_system_object(
		self,
		fso: Connection,
		prefix: str,
		onRequest=None,
		onResponse=None,
	) -> None:
		"""파일 접근 연결을 Application 소유 prefix 라우트에 연결한다."""
		if self.running:
			raise RuntimeError('실행 중에는 파일 경로를 등록할 수 없습니다')
		self.router.add(filesystem_handler(
			fso,
			prefix,
			on_request=onRequest,
			on_response=onResponse,
		))
		return

	def __call__(
		self,
		request: Request,
	) -> Optional[Response]:
		if request.method == 'OPTIONS' and request.uri == '*':
			return RunOptions().run(
				request,
				self.router,
			)
		matches = self.router.matches(request.path)
		if not matches:
			raise ClientError(
				'일치하는 경로가 없습니다',
				status=404,
			)
		if request.method == 'OPTIONS' and 'OPTIONS' not in matches:
			return RunOptions().run(
				request,
				self.router,
			)
		if request.method not in matches:
			raise ClientError(
				'지원하지 않는 메서드입니다',
				status=405,
			)
		if (request.reader.chunked or request.reader.remaining) and request.format is None:
			raise ClientError('본문이 있는 요청에는 Content-Type이 필요합니다')
		route, parameters = matches[request.method]
		if (request.reader.chunked or request.reader.remaining) and route.object.properties.body is None:
			raise ClientError(
				'처리기에 본문 읽기 방식이 지정되지 않았습니다',
				status=415,
			)
		request.params = parameters
		return RunRequest(route.object).run(request)
