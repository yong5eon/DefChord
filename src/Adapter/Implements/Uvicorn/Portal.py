from asyncio import (
	AbstractEventLoop,
	run_coroutine_threadsafe,
)
from concurrent.futures import (
	CancelledError,
	Future,
)
from threading import Lock
from typing import (
	Any,
	Coroutine,
	TypeVar,
)

from ....IO.RequestReader import ClientDisconnected

__all__ = (
	'Portal',
)


Result = TypeVar('Result')


class Portal:
	"""동기 핸들러의 입출력을 이벤트 루프에 전달하고 취소 시 대기를 해제한다."""

	def __init__(
		self,
		loop: AbstractEventLoop,
	):
		self.loop = loop
		self.lock = Lock()
		self.pending: set[Future[Any]] = set()
		self.closed = False
		return

	def call(
		self,
		coroutine: Coroutine[Any, Any, Result],
	) -> Result:
		with self.lock:
			if self.closed:
				coroutine.close()
				raise ClientDisconnected('Connection is closed')
			future = run_coroutine_threadsafe(
				coroutine,
				self.loop,
			)
			self.pending.add(future)
		try:
			return future.result()
		except CancelledError as error:
			raise ClientDisconnected('Connection was cancelled') from error
		finally:
			with self.lock:
				self.pending.discard(future)

	def close(self) -> None:
		with self.lock:
			self.closed = True
			for future in self.pending:
				future.cancel()
		return
