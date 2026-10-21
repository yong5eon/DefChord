from http import HTTPStatus


class Error(Exception):
	"""HTTP 응답으로 전달할 오류."""

	def __init__(
		self,
		status: int,
		reason: str,
	):
		super().__init__(reason)
		self.status = status
		self.message = HTTPStatus(status).phrase
		self.reason = reason
		return


class ClientError(Error):
	"""잘못된 클라이언트 요청."""

	def __init__(
		self,
		reason: str,
		status: int = 400,
	):
		if not 400 <= status < 500:
			raise ValueError('ClientError 상태 코드는 4xx여야 합니다')
		super().__init__(
			status,
			reason,
		)
		return
