from asyncio import (
	Queue,
	create_task,
	get_running_loop,
	to_thread,
	wait_for,
)
from contextlib import suppress
from importlib.util import find_spec
from unittest import (
	IsolatedAsyncioTestCase,
	skipUnless,
)

from DefEssential.IO.RequestReader import ClientDisconnected


@skipUnless(find_spec('a2wsgi') is not None, 'a2wsgi 필요')
class InputTests(IsolatedAsyncioTestCase):
	async def asyncSetUp(self):
		from DefEssential.Adapter.Implements.Uvicorn.HTTP import Input
		from DefEssential.Adapter.Implements.Uvicorn.Portal import Portal

		self.events = Queue()
		self.portal = Portal(get_running_loop())
		self.body = Input(
			self.events.get,
			self.portal,
			1,
		)
		self.pump = create_task(self.body.pump())
		return

	async def asyncTearDown(self):
		from asyncio import CancelledError

		self.portal.close()
		if self.pump is not None:
			self.pump.cancel()
			with suppress(CancelledError):
				await self.pump
		return

	async def test_lines_share_the_single_receive_pump(self):
		for data, more in (
			(b'a', True),
			(b'\nb\nc', True),
			(b'', False),
		):
			await self.events.put({
				'type': 'http.request',
				'body': data,
				'more_body': more,
			})
		self.assertEqual(await wait_for(to_thread(self.body.readline, 1), 2), b'a')
		self.assertEqual(await wait_for(to_thread(self.body.readline), 2), b'\n')
		self.assertEqual(await wait_for(to_thread(self.body.readlines), 2), [
			b'b\n',
			b'c',
		])
		self.assertFalse(self.body.has_more)
		return

	async def test_receive_failure_unblocks_reader_and_propagates(self):
		await self.events.put({'type': 'websocket.connect'})
		with self.assertRaisesRegex(RuntimeError, 'HTTP request body'):
			await wait_for(to_thread(self.body.read, 1), 2)
		pump = self.pump
		assert pump is not None
		with self.assertRaisesRegex(RuntimeError, 'HTTP request body'):
			await pump
		self.pump = None
		return

	async def test_disconnect_unblocks_reader(self):
		await self.events.put({'type': 'http.disconnect'})
		with self.assertRaises(ClientDisconnected):
			await wait_for(to_thread(self.body.read, 1), 2)
		return

	async def test_portal_close_unblocks_pending_read(self):
		from asyncio import sleep

		reader = create_task(to_thread(self.body.read, 1))
		while not self.portal.pending:
			await sleep(0)
		self.portal.close()
		with self.assertRaises(ClientDisconnected):
			await wait_for(reader, 2)
		return
