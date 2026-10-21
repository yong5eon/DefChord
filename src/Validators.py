from abc import (
	ABC,
	abstractmethod,
)
from typing import (
	Any,
	Mapping,
	Optional,
	Sequence,
	Union,
)

from .Error import (
	ClientError,
	Error,
)
from .Request import Request
from .Validator import (
	Pattern,
	Validator,
)
from .Validator.Patterns.Object import (
	IsMappingOf,
	IsRequiredIn,
)


class Origin:
	"""Allow only configured origins and provide the CORS response policy."""

	def __init__(
		self,
		origin: Union[str, Sequence[str], None] = None,
		all: bool = False,
		error: Optional[Error] = None,
	):
		self.matches = tuple(origin) if origin is not None and not isinstance(origin, str) else (
			(origin,) if origin is not None else ()
		)
		self.all = all
		self.error = error
		return

	def allows(
		self,
		origin: Optional[str],
	) -> bool:
		return self.all or origin in self.matches

	def __call__(
		self,
		request: Request,
	) -> None:
		if not self.allows(request.header('Origin')):
			raise self.error if self.error is not None else ClientError(
				'Origin not allowed',
				status=403,
			)
		return


class Credentials(ABC):
	"""Define credential extraction and documentation metadata."""

	@abstractmethod
	def __call__(
		self,
		request: Request,
	) -> Any:
		raise NotImplementedError

	@property
	@abstractmethod
	def name(self) -> str:
		raise NotImplementedError

	@property
	@abstractmethod
	def format(self) -> dict:
		raise NotImplementedError

	@property
	def headers(self) -> Sequence[str]:
		return ()


class Authorization(ABC):
	"""Define validation of extracted credentials and conversion to sessions."""

	@abstractmethod
	def __call__(
		self,
		credentials: Any,
	) -> Any:
		raise NotImplementedError


class Auth:
	"""Perform required or optional authentication and attach a session to the request."""

	def __init__(
		self,
		auth: Authorization,
		credentials: Credentials,
		optional: bool = False,
		error: Optional[Error] = None,
	):
		self.auth = auth
		self.credentials = credentials
		self.optional = optional
		self.error = error
		return

	def __call__(
		self,
		request: Request,
	) -> None:
		try:
			credentials = self.credentials(request)
			if credentials is None or credentials == '':
				if self.optional:
					return
				raise ClientError(
					'Missing credentials',
					status=401,
				)
			request.session = self.auth(credentials)
		except ClientError as error:
			if self.error is not None:
				raise self.error from error
			raise
		return


class Parameters:
	"""Validate and convert mapped path parameters and retain their schemas."""

	def __init__(
		self,
		parameters: Mapping[str, Union[Pattern, Validator, Sequence[Pattern]]],
		format: Optional[Mapping[str, object]] = None,
	):
		self.va = Validator(IsMappingOf(dict(parameters)))
		self.keys = tuple(parameters)
		self.format = format
		return

	def validate(
		self,
		values: dict,
	) -> dict:
		try:
			return self.va(dict(values))
		except (ValueError, TypeError) as error:
			raise ClientError(str(error)) from error

	def __call__(
		self,
		request: Request,
	) -> None:
		request.params = self.validate(request.params)
		return


class QueryString(Parameters):
	"""Enforce required query keys and validate their values."""

	def __init__(
		self,
		qs: Mapping[str, Union[Pattern, Validator, Sequence[Pattern]]],
		requires: Union[str, Sequence[str], None] = None,
		requiresError: Optional[Error] = None,
		format: Optional[Mapping[str, object]] = None,
	):
		super().__init__(
			qs,
			format=format,
		)
		keys = (requires,) if isinstance(requires, str) else tuple(requires or ())
		self.required_keys = keys
		self.va = Validator(
			IsRequiredIn(
				*keys,
				error=requiresError,
			),
			IsMappingOf(dict(qs)),
		)
		return

	def __call__(
		self,
		request: Request,
	) -> None:
		request.args = self.validate(request.args)
		return


class Headers(QueryString):
	"""Validate request headers case-insensitively."""

	def __init__(
		self,
		headers: Mapping[str, Union[Pattern, Validator, Sequence[Pattern]]],
		requires: Union[str, Sequence[str], None] = None,
		requiresError: Optional[Error] = None,
		format: Optional[Mapping[str, object]] = None,
	):
		required = (requires,) if isinstance(requires, str) else tuple(requires or ())
		super().__init__(
			{key.lower(): value for key, value in headers.items()},
			requires=tuple(key.lower() for key in required),
			requiresError=requiresError,
			format=format,
		)
		self.headers = tuple(headers)
		self.keys = tuple(headers)
		return

	def __call__(
		self,
		request: Request,
	) -> None:
		values = self.validate({
			key.lower(): value for key, value in request.headers()
		})
		for key in self.headers:
			value = values[key.lower()]
			if value is not None:
				request.header(
					key,
					str(value),
				)
		return
