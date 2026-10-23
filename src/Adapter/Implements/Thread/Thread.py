from ...Adapter import Adapter
from ....Application import Application
from .Server import serve as serve_threaded


class ThreadAdapter(Adapter):
	"""Use DefEssential's built-in threaded HTTP server."""

	def create_server(
		self,
		host: str,
		port: int,
	):
		server = serve_threaded(
			host,
			port,
			self.app,
		)
		server.adapter = self
		return server


def serve(
	host: str,
	port: int,
	app: Application,
):
	return ThreadAdapter(app).create_server(host, port)
