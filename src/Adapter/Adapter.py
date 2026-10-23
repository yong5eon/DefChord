from abc import ABC
from logging import getLogger
from typing import Optional

from ..Application import Application
from ..Error import Error
from ..Request import Request
from ..Response import Response


class Adapter(ABC):
	"""Bridge an Application request to an external server protocol."""

	def __init__(
		self,
		app: Application,
	):
		if not isinstance(app, Application):
			raise TypeError('app must be an Application')
		self.app = app
		return

	def application(
		self,
		request: Request,
	) -> Optional[Response]:
		"""Invoke the shared application using the adapter's internal request."""
		return self.app(request)

	def dispatch(
		self,
		request: Request,
	) -> None:
		observations = []
		response: Optional[Response] = None
		status = 500
		failure = None
		try:
			try:
				for extension in self.app.exts.values():
					context = extension.begin(request)
					observations.append((extension, context))
				response = self.app(request)
			except Error as error:
				status = error.status
				failure = error
				if request.writer.started:
					raise
				response = Response(
					status=error.status,
					body=error.reason.encode('utf-8'),
					format='text/plain',
					charset='utf-8',
				)
			except Exception as error:
				failure = error
				if request.writer.started:
					raise
				getLogger('DefEssential.Adapter').exception('Unexpected error while handling request')
				response = Response(
					status=500,
					body=b'Internal Server Error',
				)
			if response is not None:
				status = response.status
				request.writer.response(
					response,
					filtered=True,
				)
			elif not request.writer.ended:
				raise RuntimeError('Response was neither returned nor completed successfully')
			else:
				status = getattr(request.writer.writer, 'status', status)
		finally:
			if response is not None:
				try:
					response.close()
				except Exception:
					getLogger('DefEssential.Adapter').exception('Response body cleanup failed')
			for extension, context in reversed(observations):
				try:
					extension.end(
						request,
						context,
						status,
						failure,
					)
				except Exception:
					getLogger('DefEssential.Adapter').exception('Extension request observation cleanup failed')
		return
