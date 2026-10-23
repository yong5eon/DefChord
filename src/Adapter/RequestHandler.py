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
	"""전송 계층과 무관하게 요청 관찰, 오류 응답, 자원 정리를 수행한다."""
	logger = getLogger('DefEssential.Server')
	response = None
	request = None
	observations = []
	status = 500
	failure = None
	try:
		try:
			request = create_request()
			for extension in application.exts.values():
				context = extension.begin(request)
				observations.append((
					extension,
					context,
				))
			response = application(request)
		except ClientDisconnected:
			raise
		except Error as error:
			status = error.status
			failure = error
			if writer.started:
				raise
			response = Response(
				status=error.status,
				headers=error.headers,
				body=error.reason.encode('utf-8'),
				format='text/plain',
				charset='utf-8',
			)
		except Exception as error:
			failure = error
			if writer.started:
				raise
			logger.exception('Unexpected error while handling request')
			response = Response(
				status=500,
				body=b'Internal Server Error',
			)
		if response is not None:
			status = response.status
			writer.response(
				response,
				filtered=True,
			)
		elif not writer.ended:
			raise RuntimeError('Response was neither returned nor completed successfully')
		else:
			status = writer.status
	except ConnectionError as error:
		failure = error
		logger.warning('Client disconnected: %s', error)
		raise
	except OSError as error:
		failure = error
		logger.warning('Connection closed while sending response', exc_info=True)
		raise
	except Exception as error:
		failure = error
		logger.exception('Response transmission failed: closing connection without another error response')
		raise
	finally:
		if response is not None:
			try:
				response.close()
			except Exception as error:
				failure = error
				logger.exception('Response body cleanup failed')
		if request is not None:
			for extension, context in reversed(observations):
				try:
					extension.end(
						request,
						context,
						status,
						failure,
					)
				except Exception:
					logger.exception('Extension request observation cleanup failed')
	return
