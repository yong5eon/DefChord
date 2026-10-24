from logging import (
	INFO,
	basicConfig,
	getLogger,
)
from pathlib import Path
from sys import (
	path,
	stdout,
)
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


class LogApplicationStartup(ApplicationStartup):
	def __call__(self) -> None:
		getLogger('Sample').info('Application started')
		return


class LogApplicationCleanup(ApplicationCleanup):
	def __call__(self) -> None:
		getLogger('Sample').info('Application stopped')
		return


class LogApplicationRequest(ApplicationRequest):
	def __call__(
		self,
		request: Request,
	) -> Request:
		getLogger('Sample').info(
			'Request %s: %s %s',
			request.id,
			request.method,
			request.uri,
		)
		return request


class LogApplicationResponse(ApplicationRequestResponse):
	def __call__(
		self,
		request: Request,
		response: Optional[Response],
	) -> Optional[Response]:
		status = response.status if response is not None else 'direct output'
		getLogger('Sample').info(
			'Request %s completed: %s',
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
		getLogger('Sample').error(
			'Request %s failed: %s',
			request.id,
			error,
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
	"""JPG 파일 응답을 샘플 PNG 파일 응답으로 교체한다."""

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
	"""기본 Extension 인스턴스로 샘플 앱을 구성한다."""
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
		on_startup=LogApplicationStartup(),
		on_cleanup=LogApplicationCleanup(),
		on_request=LogApplicationRequest(),
		on_request_response=LogApplicationResponse(),
		on_request_error=LogApplicationError(),
	)
	app.add(RunGet)
	app.add(RunPost)
	app.add(RunPut)
	app.add(RunDelete)
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
	basicConfig(
		level=INFO,
		stream=stdout,
		force=True,
	)
	app = create_application()
	with Server(
		'127.0.0.1',
		8000,
		app,
	) as server:
		server.run()
