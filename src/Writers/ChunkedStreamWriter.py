from .StreamWriter import StreamWriter


class ChunkedStreamWriter(StreamWriter):
	"""HTTP/1.1 Chunked 프레이밍으로 직접 출력한다."""

	chunked = True

	def chunk(
		self,
		data: bytes,
	) -> None:
		self.write(data)
		self.flush()
		return
