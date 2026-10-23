from .StreamWriter import StreamWriter

__all__ = (
	'ChunkedStreamWriter',
)


class ChunkedStreamWriter(StreamWriter):
	"""Write directly using HTTP/1.1 chunked framing."""

	chunked = True

	def chunk(
		self,
		data: bytes,
	) -> None:
		self.write(data)
		self.flush()
		return
