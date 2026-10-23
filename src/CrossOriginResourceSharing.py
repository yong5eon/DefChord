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


class CrossOriginResourceSharing:
	"""요청 설정에 따라 Cross-Origin Resource Sharing 정책을 적용한다."""

	def __init__(
		self,
		properties: RequestProperties,
	):
		self.request_properties = properties
		return

	def origin_policies(self) -> Sequence[Origin]:
		value = self.request_properties.origin
		if isinstance(value, Origin):
			return (value,)
		if isinstance(value, Sequence):
			return tuple(item for item in value if isinstance(item, Origin))
		return ()

	def has_origin_policy(self) -> bool:
		return bool(self.origin_policies())

	def validate_origin(
		self,
		request: Request,
	) -> None:
		policies = self.origin_policies()
		if policies:
			if any(policy.allows(request.header('Origin')) for policy in policies):
				return
			error = next((policy.error for policy in policies if policy.error is not None), None)
			raise error if error is not None else ClientError(
				'Origin not allowed',
				status=403,
			)
		return

	def allowed_request_headers(self) -> list[str]:
		headers = []
		if isinstance(self.request_properties.headers, Headers):
			headers.extend(self.request_properties.headers.headers)
		if isinstance(self.request_properties.auth, Auth):
			headers.extend(self.request_properties.auth.credentials.headers)
		if self.request_properties.body is not None:
			headers.append('Content-Type')
		return list(dict.fromkeys(headers))

	def apply_to_response(
		self,
		request: Request,
		response: Response,
		*,
		preflight: bool = False,
	) -> Response:
		if not self.has_origin_policy():
			return response
		origin = request.header('Origin')
		if origin is None:
			return response
		self.validate_origin(request)
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
		if self.request_properties.auth is not None:
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
