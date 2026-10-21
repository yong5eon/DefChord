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
	"""허용한 Origin만 통과시키며 CORS 응답 정책을 제공한다."""

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
				'허용하지 않는 Origin',
				status=403,
			)
		return


class Credentials(ABC):
	"""요청에서 인증 정보를 추출하고 문서 형식을 제공하는 계약."""

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
	"""추출한 인증 정보를 검증하고 세션으로 변환하는 계약."""

	@abstractmethod
	def __call__(
		self,
		credentials: Any,
	) -> Any:
		raise NotImplementedError


class Auth:
	"""필수 또는 선택적 인증을 수행하고 요청에 세션을 연결한다."""

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
					'인증 정보가 없습니다',
					status=401,
				)
			request.session = self.auth(credentials)
		except ClientError as error:
			if self.error is not None:
				raise self.error from error
			raise
		return


class Parameters:
	"""매핑 기반 경로 매개변수를 검증·변환하고 스키마를 보관한다."""

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
	"""필수 쿼리 키와 값 검증을 적용한다."""

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
	"""대소문자를 구분하지 않고 요청 헤더를 검증한다."""

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
