from logging import (
	DEBUG,
	ERROR,
	WARNING,
	INFO,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
	LogRecord,
)
from copy import copy
from pathlib import Path
from sys import path
from typing import Optional

from DefEssential import (
	Application,
	ApplicationCleanup,
	ApplicationRequest,
	ApplicationRequestError,
	ApplicationRequestResponse,
	ApplicationStartup,
	ExtensionRequest,
	ExtensionRequestResponse,
	Request,
	Response,
)
from DefEssential.Adapter.Implements.Python import Server
from DefEssential.Extensions import (
	File,
	FileSystem,
	Status,
	Ping,
	Metrics,
	Specifications,
	Swagger,
)
from DefEssential.Responses import ResponseFile
from DefEssential.Utils.FileSystemObject.Implements.FileSystem import (
	Configuration,
	Connection,
)

if __name__ == '__main__' and not __package__:
	path.insert(
		0,
		str(Path(__file__).resolve().parent.parent),
	)

from samples.runners.Authentication import (
	RunAuthQuery,
	RunAuthHeader,
	RunAuthCookie,
	RunAuthHTTP,
	RunAuthOAuth2Implicit,
	RunAuthOAuth2Password,
	RunAuthOAuth2ClientCredentials,
	RunAuthOAuth2AuthorizationCode,
	ImplicitToken,
	AuthorizationCodeToken,
	PasswordToken,
	ClientCredentialsToken,
)
from samples.runners.ContentValidation import (
	RunContentBool,
	RunContentInteger,
	RunContentNumber,
	RunContentString,
	RunContentArray,
	RunContentObject,
)
from samples.runners.Requests import (
	RunDelete,
	RunHandledError,
	RunGet,
	RunPost,
	RunPut,
	RunUpload,
)
from samples.runners.Streaming import (
	RunChunkedStreamIn,
	RunChunkedStreamOut,
	RunServerSentEvent,
	RunStreamIn,
	RunStreamOut,
	RunWebSocket,
)



class LoggingFormatter(Formatter):
	default_msec_format = '%s.%03d'

	def __init__(self) -> None:
		super().__init__(
			'%(asctime)s %(levelname)-8s %(name)s %(message)s',
		)
		return

	def format(
		self,
		record: LogRecord,
	) -> str:
		text = super().format(copy(record))
		if record.levelno >= ERROR:
			color = '\x1b[31m'
		elif record.levelno >= WARNING:
			color = '\x1b[33m'
		elif record.levelno >= INFO:
			color = '\x1b[37m'
		else:
			color = '\x1b[90m'
		return '\n'.join(f'{color}{line}\x1b[0m' for line in text.split('\n'))


class LoggingSetup(ApplicationStartup):
	"""Configure sample-specific output in the first startup hook."""

	def __init__(self) -> None:
		sources = (
			Filter('Sample'),
			Filter('DefEssential'),
		)
		self.handler = StreamHandler()
		self.handler.set_name('Sample')
		self.handler.setFormatter(LoggingFormatter())
		self.handler.addFilter(lambda record: any(source.filter(record) for source in sources))
		return

	def __call__(self) -> None:
		root = getLogger()
		root.setLevel(DEBUG)
		if not any(handler.name == self.handler.name for handler in root.handlers):
			root.addHandler(self.handler)
		return


class LogApplicationStartup(ApplicationStartup):
	def __call__(self) -> None:
		getLogger('Sample').debug('Application startup hook completed')
		return


class LogApplicationCleanup(ApplicationCleanup):
	def __call__(self) -> None:
		getLogger('Sample').debug('Application cleanup hook completed')
		return


class LogApplicationRequest(ApplicationRequest):
	def __call__(
		self,
		request: Request,
	) -> Request:
		getLogger('Sample').debug(
			'Application request hook completed: request_id=%s',
			request.id,
		)
		return request


class LogApplicationResponse(ApplicationRequestResponse):
	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		status = response.status if response is not None else 'direct output'
		getLogger('Sample').debug(
			'Application response hook completed: request_id=%s status=%s',
			request.id,
			status,
		)
		return response


class LogApplicationError(ApplicationRequestError):
	def __call__(
		self,
		request: Request,
		error: Exception,
	) -> None:
		getLogger('Sample').debug(
			'Application error hook completed: request_id=%s error_type=%s',
			request.id,
			type(error).__name__,
		)
		return


class AddJpegExtension(ExtensionRequest):
	def __call__(
		self,
		request: Request,
	) -> Request:
		request.params['path'] += '.jpg'
		return request


class ReplaceWithPng(ExtensionRequestResponse):
	"""Replace a JPG file response with the sample PNG file."""

	def __init__(
		self,
		file: Path,
	):
		self.file = file
		return

	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		if response is None:
			return None
		return ResponseFile(self.file)


def create_application() -> Application:
	"""Configure the sample application with built-in extension instances."""
	resources = Path(__file__).resolve().parent / 'res'
	app = Application(
		exts=(
			Metrics('/metrics'),
			Status(
				'/status',
				metrics_uri='/metrics',
			),
			Specifications(
				'/api/doc',
				title='DefEssential HTTP Sample',
			),
			Swagger(
				'/swagger',
				spec_uri='/api/doc',
			),
			Ping('/ping'),
			File(
				'/',
				resources / 'html' / 'welcome.html',
			),
			File(
				'/favicon.ico',
				resources / 'favicon.ico',
			),
			FileSystem(
				'/css',
				Connection(Configuration(str(resources / 'css'))),
			),
			FileSystem(
				'/thumbs/request',
				Connection(Configuration(str(resources / 'images'))),
				on_request=AddJpegExtension(),
			),
			FileSystem(
				'/thumbs/response',
				Connection(Configuration(str(resources / 'images'))),
				on_request=AddJpegExtension(),
				on_request_response=ReplaceWithPng(resources / 'images' / 'sample.png'),
			),
		),
		on_startup=(
			LoggingSetup(),
			LogApplicationStartup(),
		),
		on_cleanup=LogApplicationCleanup(),
		on_request=LogApplicationRequest(),
		on_request_response=LogApplicationResponse(),
		on_request_error=LogApplicationError(),
	)
	app.add(RunGet)
	app.add(RunPost)
	app.add(RunPut)
	app.add(RunDelete)
	app.add(RunHandledError)
	app.add(RunUpload)
	app.add(RunStreamIn)
	app.add(RunStreamOut)
	app.add(RunChunkedStreamIn)
	app.add(RunChunkedStreamOut)
	app.add(RunServerSentEvent)
	app.add(RunWebSocket)
	app.add(RunAuthQuery)
	app.add(RunAuthHeader)
	app.add(RunAuthCookie)
	app.add(RunAuthHTTP)
	app.add(RunAuthOAuth2Implicit)
	app.add(RunAuthOAuth2Password)
	app.add(RunAuthOAuth2ClientCredentials)
	app.add(RunAuthOAuth2AuthorizationCode)
	app.add(ImplicitToken)
	app.add(AuthorizationCodeToken)
	app.add(PasswordToken)
	app.add(ClientCredentialsToken)
	app.add(RunContentBool)
	app.add(RunContentInteger)
	app.add(RunContentNumber)
	app.add(RunContentString)
	app.add(RunContentArray)
	app.add(RunContentObject)
	return app


if __name__ == '__main__':
	app = create_application()
	with Server(
		'127.0.0.1',
		8000,
		app,
	) as server:
		server.run()
