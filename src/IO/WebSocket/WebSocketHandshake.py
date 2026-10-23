from base64 import (
	b64decode,
	b64encode,
)
from hashlib import sha1
from typing import Optional

from ...Error import ClientError
from ...Request import Request
from ...Response import Response


class WebSocketHandshake:
	"""WebSocket 열기 핸드셰이크 요청을 검증하고 101 응답을 만든다."""

	GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
	VERSION = '13'

	def __init__(
		self,
		request: Request,
	):
		self.request = request
		return

	def tokens(
		self,
		name: str,
	) -> list[str]:
		value = self.request.header(name) or ''
		return [token.strip() for token in value.split(',') if token.strip()]

	@property
	def protocols(self) -> list[str]:
		"""클라이언트가 요청한 서브프로토콜을 요청 순서대로 반환한다."""
		return self.tokens('Sec-WebSocket-Protocol')

	def validate(self) -> str:
		"""핸드셰이크 요청을 검사하고 Sec-WebSocket-Key를 반환한다."""
		if self.request.method != 'GET':
			raise ClientError('WebSocket handshake requires GET')
		if self.request.writer.version != 'HTTP/1.1':
			raise ClientError('WebSocket handshake requires HTTP/1.1')
		if 'websocket' not in (token.lower() for token in self.tokens('Upgrade')):
			raise ClientError(
				'WebSocket upgrade is required',
				status=426,
				headers={'Upgrade': 'websocket'},
			)
		if 'upgrade' not in (token.lower() for token in self.tokens('Connection')):
			raise ClientError('Connection: Upgrade is required')
		if self.request.header('Sec-WebSocket-Version') != self.VERSION:
			raise ClientError(
				'Unsupported WebSocket version',
				status=426,
				headers={'Sec-WebSocket-Version': self.VERSION},
			)
		key = self.request.header('Sec-WebSocket-Key')
		try:
			valid = key is not None and len(b64decode(key, validate=True)) == 16
		except ValueError:
			valid = False
		if key is None or not valid:
			raise ClientError('Invalid Sec-WebSocket-Key')
		return key

	def accept_key(
		self,
		key: str,
	) -> str:
		return b64encode(sha1((key + self.GUID).encode('ascii')).digest()).decode('ascii')

	def response(
		self,
		protocol: Optional[str] = None,
	) -> Response:
		key = self.validate()
		if protocol is not None and protocol not in self.protocols:
			raise ValueError('Selected subprotocol was not requested by the client')
		headers = {
			'Upgrade': 'websocket',
			'Connection': 'Upgrade',
			'Sec-WebSocket-Accept': self.accept_key(key),
		}
		if protocol is not None:
			headers['Sec-WebSocket-Protocol'] = protocol
		return Response(
			status=101,
			headers=headers,
		)
