from dataclasses import dataclass
from http.cookies import (
	CookieError,
	SimpleCookie,
)
from typing import (
	Any,
	Optional,
	Sequence,
)

from .Error import ClientError
from .Request import Request
from .Validators import Credentials


@dataclass(frozen=True)
class HTTPAuthorization:
	"""Represent the scheme and credentials of an HTTP authentication header."""

	scheme: str
	credentials: str


class Query(Credentials):
	"""Extract a single credential value from the query string."""

	def __init__(
		self,
		name: str,
	):
		self.key = name
		return

	def __call__(
		self,
		request: Request,
	) -> Optional[str]:
		value = request.qs.get(self.key)
		if value is not None and not isinstance(value, str):
			raise ClientError(
				'Credential query parameter must have a single value',
				status=401,
			)
		return value

	@property
	def name(self) -> str:
		return 'Query'

	@property
	def format(self) -> dict:
		return {
			'type': 'apiKey',
			'in': 'query',
			'name': self.key,
		}


class Header(Query):
	"""Extract credentials from the specified header."""

	def __call__(
		self,
		request: Request,
	) -> Optional[str]:
		return request.header(self.key)

	@property
	def name(self) -> str:
		return 'Header'

	@property
	def format(self) -> dict:
		return {
			'type': 'apiKey',
			'in': 'header',
			'name': self.key,
		}

	@property
	def headers(self) -> Sequence[str]:
		return (self.key,)


class Cookie(Query):
	"""Extract the value of the specified cookie."""

	def __call__(
		self,
		request: Request,
	) -> Optional[str]:
		value = request.header('Cookie')
		if value is None:
			return None
		cookies: SimpleCookie = SimpleCookie()
		try:
			cookies.load(value)
		except CookieError as error:
			raise ClientError(
				'Invalid authentication cookie',
				status=401,
			) from error
		cookie = cookies.get(self.key)
		return cookie.value if cookie is not None else None

	@property
	def name(self) -> str:
		return 'Cookie'

	@property
	def format(self) -> dict:
		return {
			'type': 'apiKey',
			'in': 'cookie',
			'name': self.key,
		}


class HTTP(Credentials):
	"""Parse the Authorization header and verify the specified scheme."""

	def __init__(
		self,
		scheme: str,
		format: Optional[str] = None,
	):
		self.scheme = scheme
		self.fmt = format
		return

	def __call__(
		self,
		request: Request,
	) -> Optional[HTTPAuthorization]:
		value = request.header('Authorization')
		if value is None:
			return None
		scheme, separator, credentials = value.partition(' ')
		if not separator or not credentials.strip() or scheme.lower() != self.scheme.lower():
			raise ClientError(
				'Invalid authentication scheme or credentials',
				status=401,
			)
		return HTTPAuthorization(
			scheme=scheme,
			credentials=credentials.strip(),
		)

	@property
	def name(self) -> str:
		return 'HTTP'

	@property
	def format(self) -> dict:
		value = {
			'type': 'http',
			'scheme': self.scheme.lower(),
		}
		if self.fmt is not None:
			value['bearerFormat'] = self.fmt
		return value

	@property
	def headers(self) -> Sequence[str]:
		return ('Authorization',)


class OAuth2Implicit(HTTP):
	"""Configure bearer authentication metadata for the OAuth2 implicit flow."""

	flow = 'implicit'

	def __init__(
		self,
		authorizationUrl: Optional[str] = None,
	):
		super().__init__('Bearer')
		self.options: dict[str, Any] = {'scopes': {}}
		if authorizationUrl is not None:
			self.options['authorizationUrl'] = authorizationUrl
		return

	@property
	def name(self) -> str:
		return type(self).__name__

	@property
	def format(self) -> dict:
		return {
			'type': 'oauth2',
			'flows': {self.flow: dict(self.options)},
		}


class OAuth2Password(OAuth2Implicit):
	"""Configure token and refresh URLs for the OAuth2 password flow."""

	flow = 'password'

	def __init__(
		self,
		tokenUrl: Optional[str] = None,
		refreshUrl: Optional[str] = None,
	):
		super().__init__()
		if tokenUrl is not None:
			self.options['tokenUrl'] = tokenUrl
		if refreshUrl is not None:
			self.options['refreshUrl'] = refreshUrl
		return


class OAuth2ClientCredentials(OAuth2Password):
	"""Represent the OAuth2 clientCredentials flow."""

	flow = 'clientCredentials'


class OAuth2AuthorizationCode(OAuth2Password):
	"""Configure authorization and token URLs for the OAuth2 authorizationCode flow."""

	flow = 'authorizationCode'

	def __init__(
		self,
		authorizationUrl: Optional[str] = None,
		tokenUrl: Optional[str] = None,
	):
		super().__init__(tokenUrl=tokenUrl)
		if authorizationUrl is not None:
			self.options['authorizationUrl'] = authorizationUrl
		return
