from collections.abc import (
	Mapping,
	Sequence,
)
from copy import deepcopy
from re import (
	fullmatch,
	sub,
)
from typing import (
	Any,
	Optional,
	Union,
)

from ..Application import Application
from ..Body import Body
from ..Content import Content
from ..Descriptor import (
	Schema,
	schema_value,
)
from ..Extension import (
	Extension,
	ExtensionCleanup,
	ExtensionRequest,
	ExtensionRequestError,
	ExtensionRequestResponse,
	ExtensionStartup,
)
from ..Request import Request
from ..IO.Readers import (
	ByteStringContentReader,
	FormUrlEncodedContentReader,
	JavaScriptObjectNotationContentReader,
	TextContentReader,
)
from ..Response import Response
from ..ResponseSpecification import ResponseSpecification
from ..Responses import ResponseJSON
from ..Validators import (
	Auth,
	Headers,
	Parameters,
	QueryString,
)
from .FileSystem import FileSystemRoute
from .Utils.Routes import (
	http_routes,
	validate_path,
)

__all__ = (
	'Specifications',
)

class Specifications(Extension):
	"""공유 라우트 목록의 현재 선언을 OpenAPI 3.1 문서로 변환한다."""

	def __init__(
		self,
		path: str,
		*,
		title: str = 'DefEssential',
		version: str = '1.0.0',
		description=None,
		on_startup: Optional[Union[
			ExtensionStartup,
			Sequence[ExtensionStartup],
		]] = None,
		on_cleanup: Optional[Union[
			ExtensionCleanup,
			Sequence[ExtensionCleanup],
		]] = None,
		on_request: Optional[Union[
			ExtensionRequest,
			Sequence[ExtensionRequest],
		]] = None,
		on_request_response: Optional[Union[
			ExtensionRequestResponse,
			Sequence[ExtensionRequestResponse],
		]] = None,
		on_request_error: Optional[Union[
			ExtensionRequestError,
			Sequence[ExtensionRequestError],
		]] = None,
	):
		super().__init__(
			on_startup=on_startup,
			on_cleanup=on_cleanup,
			on_request=on_request,
			on_request_response=on_request_response,
			on_request_error=on_request_error,
		)
		validate_path(path)
		self.path = path
		if not isinstance(title, str) or not title or not isinstance(version, str) or not version:
			raise ValueError('Document title and version must be non-empty strings')
		self.title = title
		self.version = version
		self.description = description
		return

	def __str__(self) -> str:
		return '{}({})'.format(type(self).__name__, self.path)

	def startup(
		self,
		application: Application,
	) -> None:
		self.application = application
		for route in http_routes(self, self.path):
			application.add_extension_route(self, route)
		super().startup(application)
		return

	def document(
		self,
	) -> dict:
		schemas: dict[str, Any] = {}
		security: dict[str, Any] = {}

		def schema(value):
			if isinstance(value, Schema):
				name = value.name
				converted = schema(value.format)
				if name in schemas and schemas[name] != converted:
					raise ValueError('Conflicting schemas with the same name: ' + name)
				schemas[name] = converted
				return {'$ref': '#/components/schemas/' + name.replace('~', '~0').replace('/', '~1')}
			return schema_value(value)

		def contents(value):
			items = (value,) if isinstance(value, Content) else tuple(value or ())
			result = {}
			for item in items:
				if not isinstance(item, Content):
					raise TypeError('Body specifications require Content instances')
				if item.format in result:
					raise ValueError('Duplicate body format: ' + item.format)
				entry = {}
				if item.schema is not None:
					entry['schema'] = schema(item.schema)
				if item.example is not None:
					entry['example'] = deepcopy(item.example)
				result[item.format] = entry
			return result

		def responses(value):
			if value is None:
				return {'default': {'description': 'No response specification declared'}}
			if isinstance(value, ResponseSpecification):
				items = (value,)
			elif isinstance(value, Mapping):
				result = {}
				for code, response in value.items():
					if fullmatch(r'default|[1-5](?:[0-9]{2}|XX)', str(code)) is None:
						raise ValueError('Invalid OpenAPI response status: ' + str(code))
					if isinstance(response, str):
						result[str(code)] = {'description': response}
					elif isinstance(response, Mapping):
						if not isinstance(response.get('description'), str):
							raise ValueError('OpenAPI responses require a description')
						result[str(code)] = deepcopy(dict(response))
					else:
						raise TypeError('Response mappings require description strings or OpenAPI response objects')
				if not result:
					raise ValueError('Response specification must not be empty')
				return result
			elif isinstance(value, Sequence) and not isinstance(value, str):
				items = value
			else:
				raise TypeError('response must be a ResponseSpecification or response mapping')
			result = {}
			for item in items:
				if not isinstance(item, ResponseSpecification):
					raise TypeError('Response lists must contain ResponseSpecification instances')
				if not 100 <= item.status <= 599:
					raise ValueError('Invalid response status code')
				code = str(item.status)
				if code in result:
					raise ValueError('Duplicate response status: ' + code)
				entry: dict[str, Any] = {'description': item.description}
				if item.content is not None:
					entry['content'] = contents(item.content)
				if item.headers is not None:
					entry['headers'] = {
						key: {'schema': schema(value)} for key, value in item.headers.items()
					}
				result[code] = entry
			if not result:
				raise ValueError('Response specification must not be empty')
			return result

		paths: dict[str, Any] = {}
		custom: list[dict] = []
		for route in self.application.router.routes:
			if any(route is extension_route for extension_route in self.application.extension_routes):
				continue
			properties = route.object.properties
			operation = {
				'operationId': route.method + ':' + route.url,
				'responses': responses(properties.response),
			}
			for name in (
				'summary',
				'description',
			):
				value = getattr(properties, name)
				if value is not None:
					operation[name] = value
			if properties.tags is not None:
				operation['tags'] = [properties.tags] if isinstance(properties.tags, str) else list(properties.tags)
			parameters = []
			path_names = [match.group(1) for match in route.variable.finditer(route.url)]
			if isinstance(route, FileSystemRoute):
				path_names = ['path']
				operation['x-defessential-catch-all'] = True
			for location, check, names in (
				('path', properties.parameters, path_names),
				('query', properties.qs, ()),
				('header', properties.headers, ()),
			):
				if isinstance(check, Parameters):
					formats = check.format if check.format is not None else {}
					keys = list(check.keys)
					keys.extend(key for key in formats if key not in keys)
					if isinstance(check, QueryString) and not isinstance(check, Headers):
						keys.extend(key for key in check.required_keys if key not in keys)
					keys.extend(name for name in names if name not in keys)
				else:
					formats = {}
					keys = list(names)
				for key in keys:
					value = formats.get(key)
					required = location == 'path'
					if isinstance(check, QueryString):
						required = key.lower() in check.required_keys if isinstance(check, Headers) else key in check.required_keys
					entry = {
						'name': key,
						'in': location,
						'required': required,
						'schema': schema(value) if value is not None else {},
					}
					parameters.append(entry)
			if parameters:
				operation['parameters'] = parameters
			if isinstance(properties.body, Body):
				body_content = properties.body.content
				if not body_content:
					for reader, media in (
						(JavaScriptObjectNotationContentReader, 'application/json'),
						(FormUrlEncodedContentReader, 'application/x-www-form-urlencoded'),
						(TextContentReader, 'text/*'),
						(ByteStringContentReader, '*/*'),
					):
						if isinstance(properties.body.reader, reader):
							body_content = (Content(media),)
							break
				if not body_content:
					raise ValueError('Custom readers require a Content specification: ' + route.url)
				operation['requestBody'] = {
					'required': properties.body.required,
					'content': contents(body_content),
				}
			if isinstance(properties.auth, Auth):
				credentials = properties.auth.credentials
				definition = credentials.format
				name = credentials.name
				index = 2
				while name in security and security[name] != definition:
					name = credentials.name + str(index)
					index += 1
				security[name] = definition
				operation['security'] = [{name: []}]
				if properties.auth.optional:
					operation['security'].append({})
			path = sub(
				r':([A-Za-z_][A-Za-z_0-9]*)',
				r'{\1}',
				route.url,
			)
			if isinstance(route, FileSystemRoute):
				path = route.prefix + '{path}'
			if route.method.lower() in (
				'get',
				'put',
				'post',
				'delete',
				'options',
				'head',
				'patch',
				'trace',
			):
				path_item = paths.setdefault(path, {})
				if route.method.lower() in path_item:
					raise ValueError('Conflicting OpenAPI path and method: ' + route.method + ' ' + path)
				path_item[route.method.lower()] = operation
			else:
				custom.append({
					'method': route.method,
					'path': path,
					'operation': operation,
				})
		info = {
			'title': self.title,
			'version': self.version,
		}
		if self.description is not None:
			info['description'] = self.description
		document = {
			'openapi': '3.1.0',
			'info': info,
			'paths': paths,
			'components': {
				'schemas': schemas,
				'securitySchemes': security,
			},
		}
		if custom:
			document['x-defessential-operations'] = custom
		return document

	def __call__(
		self,
		request: Request,
	) -> Response:
		return ResponseJSON(self.document())
