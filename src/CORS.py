from typing import Sequence

from .Error import ClientError
from .Request import Request
from .RequestRunner import RequestProperties
from .Response import Response
from .Validators import (
	Auth,
	Headers,
	Origin,
)


def origins(properties: RequestProperties) -> Sequence[Origin]:
	value = properties.origin
	if isinstance(value, Origin):
		return (value,)
	if isinstance(value, Sequence):
		return tuple(item for item in value if isinstance(item, Origin))
	return ()


def check_origin(
	properties: RequestProperties,
	request: Request,
) -> None:
	policies = origins(properties)
	if policies:
		if any(policy.allows(request.header('Origin')) for policy in policies):
			return
		error = next((policy.error for policy in policies if policy.error is not None), None)
		raise error if error is not None else ClientError(
			'허용하지 않는 Origin',
			status=403,
		)
	return


def allow_headers(properties: RequestProperties) -> list[str]:
	headers = []
	if isinstance(properties.headers, Headers):
		headers.extend(properties.headers.headers)
	if isinstance(properties.auth, Auth):
		headers.extend(properties.auth.credentials.headers)
	if properties.body is not None:
		headers.append('Content-Type')
	return list(dict.fromkeys(headers))


def apply_cors(
	properties: RequestProperties,
	request: Request,
	response: Response,
	*,
	preflight: bool = False,
) -> Response:
	if not origins(properties):
		return response
	origin = request.header('Origin')
	if origin is None:
		return response
	check_origin(
		properties,
		request,
	)
	response.header(
		'Access-Control-Allow-Origin',
		origin,
	)
	vary = response.header('Vary')
	fields = [item.strip() for item in vary.split(',')] if vary else []
	if 'origin' not in (item.lower() for item in fields) and '*' not in fields:
		fields.append('Origin')
	response.header(
		'Vary',
		', '.join(fields),
	)
	if properties.auth is not None:
		response.header(
			'Access-Control-Allow-Credentials',
			'true',
		)
	if not preflight:
		expose = [
			key for key, _ in response.headers()
			if key.lower() not in (
				'set-cookie',
				'content-length',
			) and not key.lower().startswith('access-control-')
		]
		if expose:
			response.header(
				'Access-Control-Expose-Headers',
				', '.join(expose),
			)
	return response
