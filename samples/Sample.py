from logging import (
	INFO,
	basicConfig,
)
from pathlib import Path

from DefStar import (
	Application,
	Origin,
	QueryString,
	Request,
	RequestRunner,
	Response,
	serve,
)
from DefStar.Runners.RunOptions import RunOptions
from DefStar.Extensions import (
	Dashboard,
	HealthCheck,
	Metrics,
	Spec,
	Swagger,
)
from DefStar.Responses import ResponseJSON
from DefStar.Validator.Patterns import (
	IsOptional,
	IsString,
)
from DefStar.Utils.FileSystemObject.Implements.FileSystem import (
	Configuration,
	Connection,
)

if __package__:
	from .Authentication import HANDLERS as AUTH_HANDLERS
	from .ContentValidation import HANDLERS as CONTENT_HANDLERS
	from .Requests import (
		RunDelete,
		RunGet,
		RunPost,
		RunPut,
		RunUpload,
	)
	from .Streaming import (
		RunChunkedStreamIn,
		RunChunkedStreamOut,
		RunServerSentEvent,
		RunStreamIn,
		RunStreamOut,
	)
else:
	from Authentication import HANDLERS as AUTH_HANDLERS
	from ContentValidation import HANDLERS as CONTENT_HANDLERS
	from Requests import (
		RunDelete,
		RunGet,
		RunPost,
		RunPut,
		RunUpload,
	)
	from Streaming import (
		RunChunkedStreamIn,
		RunChunkedStreamOut,
		RunServerSentEvent,
		RunStreamIn,
		RunStreamOut,
	)


class RunStatus(
	RequestRunner,
	method='GET',
	url='/status',
	origin=Origin(all=True),
	summary='상태 확인과 CORS',
	tags='Common',
):
	def run(
		self,
		request: Request,
	) -> Response:
		return Response()


def to_jpeg(request: Request):
	request.params['path'] += '.jpg'
	return request, None


def create_application() -> Application:
	"""호출마다 라우트와 파일 연결을 독립적으로 생성한다."""
	spec = Spec('/api/doc', title='DefStar HTTP Sample')
	app = Application(exts=(
		Metrics('/metrics'),
		Dashboard('/dashboard'),
		spec,
		Swagger('/swagger'),
		HealthCheck('/health'),
	))
	for handler in (
		RunGet,
		RunPost,
		RunPut,
		RunDelete,
		RunUpload,
		RunStreamIn,
		RunStreamOut,
		RunChunkedStreamIn,
		RunChunkedStreamOut,
		RunServerSentEvent,
		RunStatus,
		*AUTH_HANDLERS,
		*CONTENT_HANDLERS,
	):
		app.register(handler)

	class Options(
		RequestRunner,
		method='GET',
		url='/options',
		qs=QueryString(
			{
				'p': IsString(),
				'method': IsOptional(IsString()),
				'headers': IsOptional(IsString()),
				'origin': IsOptional(IsString()),
			},
			requires='p',
		),
	):
		def run(
			self,
			request: Request,
		) -> Response:
			headers = {}
			for key, header in (
				('method', 'Access-Control-Request-Method'),
				('headers', 'Access-Control-Request-Headers'),
				('origin', 'Origin'),
			):
				if request.qs[key] is not None:
					headers[header] = request.qs[key]
			response = RunOptions().run(
				Request(
					request.address,
					request.port,
					'OPTIONS',
					request.qs['p'],
					headers=headers,
				),
				app.router,
			)
			if request.qs['method'] is not None:
				return response
			document = spec.document(app)
			matches = app.router.matches(request.qs['p'])
			urls = {
				route.variable.sub(r'{\1}', route.url)
				for route, parameters in matches.values()
			}
			return ResponseJSON(
				{
					path: value for path, value in document['paths'].items()
					if path in urls
				},
				headers=dict(response.headers()),
			)

	app.register(Options)
	resources = Path(__file__).resolve().parent / 'res'
	app.add_file(resources / 'html' / 'welcome.html', '/')
	app.add_file(resources / 'favicon.ico', '/favicon.ico')
	app.add_files(resources / 'css', '/css')
	images = Connection(Configuration(str(resources / 'images')))
	images.connect()
	app.add_file_system_object(
		images,
		'/thumbs',
		onRequest=to_jpeg,
	)
	return app


if __name__ == '__main__':
	basicConfig(level=INFO)
	with serve('127.0.0.1', 8000, create_application()) as server:
		server.serve_forever()
