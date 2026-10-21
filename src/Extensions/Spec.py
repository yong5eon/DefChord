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
	TYPE_CHECKING,
)

from ..Body import Body
from ..Content import Content
from ..Descriptor import (
	Schema,
	schema_value,
)
from ..Extension import Extension
from ..Request import Request
from ..Readers import (
	ByteStringContentReader,
	FormUrlEncodedContentReader,
	JavaScriptObjectNotationContentReader,
	TextContentReader,
)
from ..Response import Response
from ..ResponseSpec import ResponseSpec
from ..Runners.RunFileSystemObject import FileSystemRoute
from ..Responses import ResponseJSON
from ..Validators import (
	Auth,
	Headers,
	Parameters,
	QueryString,
)

if TYPE_CHECKING:
	from ..Application import Application


class Spec(Extension):
	"""Application에 등록된 처리기 선언을 OpenAPI 3.1로 변환한다."""

	def __init__(
		self,
		path: str,
		*,
		title: str = 'DefStar',
		version: str = '1.0.0',
		description=None,
	):
		super().__init__(path)
		if not isinstance(title, str) or not title or not isinstance(version, str) or not version:
			raise ValueError('문서 제목과 버전에는 비어 있지 않은 문자열이 필요합니다')
		self.title = title
		self.version = version
		self.description = description
		return

	def document(
		self,
		app: 'Application',
	) -> dict:
		schemas: dict[str, Any] = {}
		security: dict[str, Any] = {}

		def schema(value):
			if isinstance(value, Schema):
				name = value.name
				converted = schema(value.format)
				if name in schemas and schemas[name] != converted:
					raise ValueError('동일한 이름의 스키마가 충돌합니다: ' + name)
				schemas[name] = converted
				return {'$ref': '#/components/schemas/' + name.replace('~', '~0').replace('/', '~1')}
			return schema_value(value)

		def contents(value):
			items = (value,) if isinstance(value, Content) else tuple(value or ())
			result = {}
			for item in items:
				if not isinstance(item, Content):
					raise TypeError('본문 명세에는 Content가 필요합니다')
				if item.format in result:
					raise ValueError('중복된 본문 형식: ' + item.format)
				entry = {}
				if item.schema is not None:
					entry['schema'] = schema(item.schema)
				if item.example is not None:
					entry['example'] = deepcopy(item.example)
				result[item.format] = entry
			return result

		def responses(value):
			if value is None:
				return {'default': {'description': '응답 명세가 선언되지 않았습니다'}}
			if isinstance(value, ResponseSpec):
				items = (value,)
			elif isinstance(value, Mapping):
				result = {}
				for code, response in value.items():
					if fullmatch(r'default|[1-5](?:[0-9]{2}|XX)', str(code)) is None:
						raise ValueError('잘못된 OpenAPI 응답 상태: ' + str(code))
					if isinstance(response, str):
						result[str(code)] = {'description': response}
					elif isinstance(response, Mapping):
						if not isinstance(response.get('description'), str):
							raise ValueError('OpenAPI 응답에는 description이 필요합니다')
						result[str(code)] = deepcopy(dict(response))
					else:
						raise TypeError('응답 매핑에는 설명 문자열 또는 OpenAPI 응답 객체가 필요합니다')
				if not result:
					raise ValueError('응답 명세는 비어 있을 수 없습니다')
				return result
			elif isinstance(value, Sequence) and not isinstance(value, str):
				items = value
			else:
				raise TypeError('response에는 ResponseSpec 또는 응답 매핑이 필요합니다')
			result = {}
			for item in items:
				if not isinstance(item, ResponseSpec):
					raise TypeError('응답 목록에는 ResponseSpec이 필요합니다')
				if not 100 <= item.status <= 599:
					raise ValueError('잘못된 응답 상태 코드')
				code = str(item.status)
				if code in result:
					raise ValueError('중복된 응답 상태: ' + code)
				entry: dict[str, Any] = {'description': item.description}
				if item.content is not None:
					entry['content'] = contents(item.content)
				if item.headers is not None:
					entry['headers'] = {
						key: {'schema': schema(value)} for key, value in item.headers.items()
					}
				result[code] = entry
			if not result:
				raise ValueError('응답 명세는 비어 있을 수 없습니다')
			return result

		paths: dict[str, Any] = {}
		custom: list[dict] = []
		for route in app.router.routes:
			if route.url in app.exts:
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
				operation['x-defstar-catch-all'] = True
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
						(ByteStringContentReader, 'application/octet-stream'),
					):
						if isinstance(properties.body.reader, reader):
							body_content = (Content(media),)
							break
				if not body_content:
					raise ValueError('사용자 정의 Reader에는 Content 명세가 필요합니다: ' + route.url)
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
					raise ValueError('OpenAPI 경로와 메서드가 충돌합니다: ' + route.method + ' ' + path)
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
			document['x-defstar-operations'] = custom
		return document

	def handle(
		self,
		app: 'Application',
		request: Request,
	) -> Response:
		return ResponseJSON(self.document(app))
