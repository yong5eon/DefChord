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
	"""Own registration state and execute a new handler instance per request."""

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
				raise TypeError('exts must contain Extension instances')
			if extension.application is not None:
				raise ValueError('Extension instances cannot be shared between Applications')
			if extension.path in self.exts:
				raise ValueError('Duplicate extension path: ' + extension.path)
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
		"""Start extensions in declaration order before serving requests."""
		with self.lifecycle_lock:
			if self.running:
				raise RuntimeError('Application is already running')
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
						getLogger('DefStar.Application').exception('Cleanup failed after extension startup failure')
				raise
			self.running = True
		return

	def stop(self) -> None:
		"""Stop started extensions in reverse order and propagate cleanup errors."""
		with self.lifecycle_lock:
			if not self.running:
				return
			self.running = False
			first_error = None
			for extension in reversed(tuple(self.exts.values())):
				try:
					extension.stop(self)
				except Exception as error:
					getLogger('DefStar.Application').exception('Extension shutdown failed')
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
			raise RuntimeError('Cannot register handlers while Application is running')
		if not issubclass(
			handler,
			RequestRunner,
		) or isabstract(handler):
			raise TypeError('A concrete RequestRunner class is required')
		properties = handler.properties
		if properties.method is None or properties.url is None:
			raise ValueError('Handlers must define method and url before registration')
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
		"""Register modules independently for each Application, even if already imported."""
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
		"""Register a file response at a fixed URL."""
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
		"""Register each file in an existing file tree as a separate route."""
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
		"""Bind a filesystem connection to an Application-owned prefix route."""
		if self.running:
			raise RuntimeError('Cannot register file paths while Application is running')
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
				'No matching route',
				status=404,
			)
		if request.method == 'OPTIONS' and 'OPTIONS' not in matches:
			return RunOptions().run(
				request,
				self.router,
			)
		if request.method not in matches:
			raise ClientError(
				'Method not allowed',
				status=405,
			)
		if (request.reader.chunked or request.reader.remaining) and request.format is None:
			raise ClientError('Content-Type is required for requests with a body')
		route, parameters = matches[request.method]
		if (request.reader.chunked or request.reader.remaining) and route.object.properties.body is None:
			raise ClientError(
				'No body reader is configured for this handler',
				status=415,
			)
		request.params = parameters
		return RunRequest(route.object).run(request)
