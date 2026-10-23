from logging import (
	INFO,
	basicConfig,
)
from pathlib import Path

from DefEssential import (
	Application,
	Request,
	RequestFilter,
	Response,
	ResponseFilter,
	serve,
)
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

from runners.Authentication import (
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
from runners.ContentValidation import (
	RunContentBool,
	RunContentInteger,
	RunContentNumber,
	RunContentString,
	RunContentArray,
	RunContentObject,
)
from runners.Requests import (
	RunDelete,
	RunGet,
	RunPost,
	RunPut,
	RunUpload,
)
from runners.Streaming import (
	RunChunkedStreamIn,
	RunChunkedStreamOut,
	RunServerSentEvent,
	RunStreamIn,
	RunStreamOut,
	RunWebSocketEcho,
)


class AddJpegExtension(RequestFilter):
	def __call__(self, request: Request):
		request.params['path'] += '.jpg'
		return request, None


class ReplaceWithPng(ResponseFilter):
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
		response: Response,
	) -> Response:
		return ResponseFile(self.file)


if __name__ == '__main__':
	basicConfig(level=INFO)
	resources = Path(__file__).resolve().parent / 'res'
	app = Application(exts=(
		Metrics('/metrics'),
		Status('/status', metrics_uri='/metrics'),
		Specifications('/api/doc', title='DefEssential HTTP Sample'),
		Swagger('/swagger', spec_uri='/api/doc'),
		Ping('/ping'),
		File('/', resources / 'html' / 'welcome.html'),
		File('/favicon.ico', resources / 'favicon.ico'),
		FileSystem('/css', Connection(Configuration(str(resources / 'css')))),
		FileSystem(
			'/thumbs/request',
			Connection(Configuration(str(resources / 'images'))),
			onRequest=AddJpegExtension(),
		),
		FileSystem(
			'/thumbs/response',
			Connection(Configuration(str(resources / 'images'))),
			onRequest=AddJpegExtension(),
			onResponse=ReplaceWithPng(resources / 'images' / 'sample.png'),
		),
	))
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
	app.add(RunWebSocketEcho)
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
	with serve('127.0.0.1', 8000, app) as server:
		server.serve_forever()
