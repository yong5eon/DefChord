from DefStar import (
	Auth,
	Authorization,
	Body,
	ClientError,
	QueryString,
	Request,
	RequestRunner,
)
from DefStar.Credentials import (
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
from DefStar.Readers import FormUrlEncodedContentReader
from DefStar.Responses import ResponseJSON
from DefStar.Validator.Patterns import (
	IsIn,
	IsObject,
	IsOptional,
	IsString,
	SetDefault,
)
from DefStar.Validator.Patterns.Object import (
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


def auth_handler(
	name,
	credentials,
):
	class RunAuth(
		RequestRunner,
		method='GET',
		url='/api/auth/' + name,
		auth=Auth(
			GetSession(),
			credentials,
		),
		summary='Authenticate sample credentials and return a session',
		tags='Auth',
	):
		def run(
			self,
			request: Request,
		) -> ResponseJSON:
			return ResponseJSON(request.session)

	return RunAuth


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


HANDLERS = (
	*(
		auth_handler(
			name,
			credentials,
		)
		for name, credentials in (
			('query', Query('credentials')),
			('header', Header('credentials')),
			('cookie', Cookie('credentials')),
			('http', HTTP('Bearer', format='JWT')),
			('oauth2/implicit', OAuth2Implicit('/api/auth/oauth2/implicit/token')),
			('oauth2/password', OAuth2Password('/api/auth/oauth2/password/token')),
			('oauth2/clientcredentials', OAuth2ClientCredentials('/api/auth/oauth2/clientcredentials/token')),
			('oauth2/authorizationcode', OAuth2AuthorizationCode('/api/auth/oauth2/authorizationcode/token')),
		)
	),
	ImplicitToken,
	AuthorizationCodeToken,
	PasswordToken,
	ClientCredentialsToken,
)
