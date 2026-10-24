from logging import getLogger
from typing import Callable

from ..Application import Application
from ..Error import Error
from ..IO.RequestReader import ClientDisconnected
from ..IO.ResponseWriter import ResponseWriter
from ..Request import Request
from ..Response import Response

__all__ = (
	'handle_request',
)


def handle_request(
	application: Application,
	create_request: Callable[[], Request],
	writer: ResponseWriter,
) -> None:
	"""전송 계층과 무관하게 오류 응답과 자원 정리를 수행한다."""
	logger = getLogger('DefEssential.Server')
	response = None
	try:
		try:
			request = create_request()
			response = application(request)
		except ClientDisconnected:
			raise
		except Error as error:
			if writer.started:
				raise
			response = Response(
				status=error.status,
				headers=error.headers,
				body=error.reason.encode('utf-8'),
				format='text/plain',
				charset='utf-8',
			)
		except Exception:
			if writer.started:
				raise
			logger.exception('Unexpected error while handling request')
			response = Response(
				status=500,
				body=b'Internal Server Error',
			)
		if response is not None:
			writer.response(
				response,
				filtered=True,
			)
		elif not writer.ended:
			raise RuntimeError('Response was neither returned nor completed successfully')
	except ConnectionError as error:
		logger.warning('Client disconnected: %s', error)
		raise
	except OSError:
		logger.warning('Connection closed while sending response', exc_info=True)
		raise
	except Exception:
		logger.exception('Response transmission failed: closing connection without another error response')
		raise
	finally:
		if response is not None:
			try:
				response.close()
			except Exception:
				logger.exception('Response body cleanup failed')
	return
