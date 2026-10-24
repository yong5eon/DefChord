from base64 import (
	b64decode,
	b64encode,
)
from hashlib import sha1
from typing import Optional

from ...Error import ClientError
from ...Request import Request
from ...Response import Response

__all__ = (
	'WebSocketHandshake',
)


class WebSocketHandshake:
	"""Validate a WebSocket opening handshake request and build a 101 response."""

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
		"""Return the subprotocols requested by the client in request order."""
		return self.tokens('Sec-WebSocket-Protocol')

	def validate(self) -> str:
		"""Validate the handshake request and return the Sec-WebSocket-Key."""
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
