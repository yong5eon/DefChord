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
	"""Compute Allow and CORS preflight responses from Application-owned routes."""

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
				'No matching route',
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
				'Preflight method not allowed',
				status=405,
			)
		properties = matches[method][0].object.properties
		if request.header('Origin') is None or not origins(properties):
			raise ClientError(
				'No CORS policy is configured for this preflight request',
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
				raise ClientError('Preflight header not allowed')
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
