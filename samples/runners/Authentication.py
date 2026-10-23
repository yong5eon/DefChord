from DefEssential import (
	Auth,
	Authorization,
	Body,
	ClientError,
	QueryString,
	Request,
	RequestRunner,
)
from DefEssential.Credentials import (
	Cookie,
	Header,
	HTTP,
	HTTPAuthorization,
	OAuth2AuthorizationCode,
	OAuth2ClientCredentials,
	OAuth2Implicit,
	OAuth2Password,
	Query,
)
from DefEssential.IO.Readers import FormUrlEncodedContentReader
from DefEssential.Responses import ResponseJSON
from DefEssential.Validator.Patterns import (
	IsIn,
	IsObject,
	IsOptional,
	IsString,
	SetDefault,
)
from DefEssential.Validator.Patterns.Object import (
	IsMappingOf,
	IsRequiredIn,
)


class GetSession(Authorization):
	"""Validate the fixed sample credential '1'; this is not an authentication server."""

	def __call__(
		self,
		credentials,
	):
		value = credentials.credentials if isinstance(credentials, HTTPAuthorization) else credentials
		if value != '1':
			raise ClientError(
				'Invalid credentials',
				status=401,
			)
		return {
			'credentials': {
				'scheme': credentials.scheme,
				'credentials': credentials.credentials,
			} if isinstance(credentials, HTTPAuthorization) else credentials,
			'extra': {'id': 0},
		}


class RunAuthQuery(
	RequestRunner,
	method='GET',
	url='/api/auth/query',
	name='RunAuth(query)',
	auth=Auth(GetSession(), Query('credentials')),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


class RunAuthHeader(
	RequestRunner,
	method='GET',
	url='/api/auth/header',
	name='RunAuth(header)',
	auth=Auth(GetSession(), Header('credentials')),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


class RunAuthCookie(
	RequestRunner,
	method='GET',
	url='/api/auth/cookie',
	name='RunAuth(cookie)',
	auth=Auth(GetSession(), Cookie('credentials')),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


class RunAuthHTTP(
	RequestRunner,
	method='GET',
	url='/api/auth/http',
	name='RunAuth(http)',
	auth=Auth(GetSession(), HTTP('Bearer', format='JWT')),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


class RunAuthOAuth2Implicit(
	RequestRunner,
	method='GET',
	url='/api/auth/oauth2/implicit',
	name='RunAuth(oauth2/implicit)',
	auth=Auth(
		GetSession(),
		OAuth2Implicit('/api/auth/oauth2/implicit/token'),
	),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


class RunAuthOAuth2Password(
	RequestRunner,
	method='GET',
	url='/api/auth/oauth2/password',
	name='RunAuth(oauth2/password)',
	auth=Auth(
		GetSession(),
		OAuth2Password('/api/auth/oauth2/password/token'),
	),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


class RunAuthOAuth2ClientCredentials(
	RequestRunner,
	method='GET',
	url='/api/auth/oauth2/clientcredentials',
	name='RunAuth(oauth2/clientcredentials)',
	auth=Auth(
		GetSession(),
		OAuth2ClientCredentials('/api/auth/oauth2/clientcredentials/token'),
	),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


class RunAuthOAuth2AuthorizationCode(
	RequestRunner,
	method='GET',
	url='/api/auth/oauth2/authorizationcode',
	name='RunAuth(oauth2/authorizationcode)',
	auth=Auth(
		GetSession(),
		OAuth2AuthorizationCode('/api/auth/oauth2/authorizationcode/token'),
	),
	summary='Authenticate sample credentials and return a session',
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return ResponseJSON(request.session)


def token_query(
	response_type,
) -> QueryString:
	return QueryString(
		{
			'response_type': IsString(IsIn(response_type)),
			'client_id': IsString(),
			'redirect_uri': IsOptional(IsString()),
			'state': IsOptional(IsString()),
		},
		requires=(
			'response_type',
			'client_id',
		),
	)


def tokens(
	values=None,
) -> ResponseJSON:
	return ResponseJSON({
		**(values if values is not None else {}),
		'access_token': '1',
		'refresh_token': '1',
	})


class ImplicitToken(
	RequestRunner,
	method='GET',
	url='/api/auth/oauth2/implicit/token',
	qs=token_query('token'),
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return tokens()


class AuthorizationCodeToken(
	RequestRunner,
	method='GET',
	url='/api/auth/oauth2/authorizationcode/token',
	qs=token_query('code'),
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return tokens()


class PasswordToken(
	RequestRunner,
	method='POST',
	url='/api/auth/oauth2/password/token',
	body=Body(FormUrlEncodedContentReader(va=IsObject(
		IsRequiredIn(
			'username',
			'password',
		),
		IsMappingOf({
			'username': IsString(),
			'password': IsString(),
			'client_id': IsOptional(IsString()),
			'client_secret': IsOptional(IsString()),
			'grant_type': (
				SetDefault('password'),
				IsString(IsIn('password')),
			),
		}),
	))),
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return tokens(request.body)


class ClientCredentialsToken(
	RequestRunner,
	method='POST',
	url='/api/auth/oauth2/clientcredentials/token',
	body=Body(FormUrlEncodedContentReader(va=IsObject())),
	tags='Auth',
):
	def run(
		self,
		request: Request,
	) -> ResponseJSON:
		return tokens(request.body)
