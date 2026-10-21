from typing import TYPE_CHECKING

from ..CORS import (
	allow_headers,
	apply_cors,
	check_origin,
	origins,
)
from ..Error import ClientError
from ..Request import Request
from ..Response import Response

if TYPE_CHECKING:
	from ..Router import Router


class RunOptions:
	"""Application 소유 라우트에서 Allow와 CORS preflight를 계산한다."""

	def run(
		self,
		request: Request,
		router: 'Router',
	) -> Response:
		if request.uri == '*':
			methods = {route.method for route in router.routes}
			methods.add('OPTIONS')
			return Response(
				status=204,
				headers={'Allow': ', '.join(sorted(methods))},
			)
		matches = router.matches(request.path)
		if not matches:
			raise ClientError(
				'일치하는 경로가 없습니다',
				status=404,
			)
		methods = sorted(set(matches) | {'OPTIONS'})
		response = Response(
			status=204,
			headers={'Allow': ', '.join(methods)},
		)
		method = request.header('Access-Control-Request-Method')
		if method is None:
			return response
		if method not in matches:
			raise ClientError(
				'지원하지 않는 preflight 메서드',
				status=405,
			)
		properties = matches[method][0].object.properties
		if request.header('Origin') is None or not origins(properties):
			raise ClientError(
				'CORS 정책이 없는 preflight 요청',
				status=403,
			)
		check_origin(
			properties,
			request,
		)
		headers = allow_headers(properties)
		requested = request.header('Access-Control-Request-Headers')
		if requested is not None:
			allowed = {name.lower() for name in headers}
			if any(name.strip().lower() not in allowed for name in requested.split(',')):
				raise ClientError('지원하지 않는 preflight 헤더')
		response.header(
			'Access-Control-Allow-Methods',
			method,
		)
		if headers:
			response.header(
				'Access-Control-Allow-Headers',
				', '.join(headers),
			)
		response.header(
			'Vary',
			'Access-Control-Request-Method, Access-Control-Request-Headers',
		)
		return apply_cors(
			properties,
			request,
			response,
			preflight=True,
		)
