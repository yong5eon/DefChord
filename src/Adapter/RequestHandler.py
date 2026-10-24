from logging import getLogger
from time import monotonic
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

LOGGER = getLogger('DefEssential.Server')


def handle_request(
	application: Application,
	create_request: Callable[[], Request],
	writer: ResponseWriter,
) -> None:
	"""전송 계층과 무관하게 오류 응답과 자원 정리를 수행한다."""
	logger = LOGGER
	started = monotonic()
	request = None
	response = None
	outcome = 'failed'
	try:
		try:
			request = create_request()
			logger.debug(
				'HTTP request received: request_id=%s method=%s',
				request.id,
				ascii(request.method[:32]),
			)
			response = application(request)
		except ClientDisconnected:
			raise
		except Error as error:
			if writer.started:
				raise
			logger.debug(
				'HTTP error response selected: request_id=%s status=%s',
				request.id if request is not None else None,
				error.status,
			)
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
			logger.exception(
				'Unexpected error while handling request: request_id=%s',
				request.id if request is not None else None,
			)
			response = Response(
				status=500,
				body=b'Internal Server Error',
			)
		if response is not None:
			logger.debug('Response transmission starting: request_id=%s status=%s', request.id if request is not None else None, response.status)
			writer.response(
				response,
				filtered=True,
			)
		elif not writer.ended:
			raise RuntimeError('Response was neither returned nor completed successfully')
		outcome = 'completed'
	except ConnectionError:
		outcome = 'disconnected'
		logger.warning(
			'Client disconnected: request_id=%s',
			request.id if request is not None else None,
		)
		raise
	except Exception:
		logger.exception(
			'Response transmission failed: closing connection without another error response request_id=%s',
			request.id if request is not None else None,
		)
		raise
	finally:
		duration = monotonic() - started
		logger.info(
			'HTTP transmission result: request_id=%s method=%s status=%s outcome=%s duration=%.6f',
			request.id if request is not None else None,
			ascii(request.method[:32]) if request is not None else None,
			writer.status if writer.started else None,
			outcome,
			duration,
		)
		if response is not None:
			try:
				logger.debug('Response body cleaning up: request_id=%s', request.id if request is not None else None)
				response.close()
				logger.debug('Response body cleaned up: request_id=%s', request.id if request is not None else None)
			except Exception:
				logger.exception(
					'Response body cleanup failed: request_id=%s',
					request.id if request is not None else None,
				)
	return
