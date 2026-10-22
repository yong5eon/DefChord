from os import (
	environ,
	getpid,
)
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .Server import Server


LOGO = r"""
▄▄▄▄▄▄            ▄▄ ▄▄▄▄▄▄▄                              ▄▄       ▄▄
███▀▀██▄         ██  ███▀▀▀▀                          ██  ▀▀       ██
███  ███ ▄█▀█▄  ▀██▀ █████   ▄██▀▀ ▄██▀▀ ▄█▀█▄ ████▄ ▀██▀ ██  ▀▀█▄ ██
███  ███ ██▄█▀   ██  ███     ▀▀██▄ ▀▀██▄ ██▄█▀ ██ ██  ██  ██ ▄█▀██ ██
██████▀  ▀█▄▄▄   ██  ███████ ▀███▀ ▀███▀ ▀█▄▄▄ ██ ██  ██  ██ ▀█▄██ ██

Just def. Let web apps do the work. You don't need to await this.
"""


def supports_color() -> bool:
	"""Use colors only for terminal output and honor NO_COLOR."""
	return (
		getattr(sys.stdout, 'isatty', lambda: False)()
		and 'NO_COLOR' not in environ
	)


def colorize_logo(logo: str) -> str:
	"""Apply the existing startup color gradient to the five banner lines."""
	colors = (
		'\033[38;5;39m',
		'\033[38;5;45m',
		'\033[38;5;51m',
		'\033[38;5;45m',
		'\033[38;5;39m',
	)
	lines = []
	art_line = 0
	for line in logo.splitlines(keepends=True):
		if line.strip() and art_line < len(colors):
			newline = '\n' if line.endswith('\n') else ''
			lines.append(
				f'{colors[art_line]}{line[:-1] if newline else line}'
				f'\033[0m{newline}',
			)
			art_line += 1
		else:
			lines.append(line)
	return ''.join(lines)


def startup(server: 'Server') -> None:
	"""Print the bound server address and actual Application registrations."""
	host, port = server.server_address[:2]
	if not isinstance(host, str):
		raise TypeError('HTTP listen address must be a string')
	address = f'[{host}]' if ':' in host else host
	logo = LOGO.rstrip()
	starting = 'Starting'
	if supports_color():
		logo = colorize_logo(logo)
		starting = f'\033[1;38;5;51m{starting}\033[0m'
	routes = server.app.router.routes
	lines = [
		logo,
		'',
		starting,
		f'  PID: {getpid()}',
		f'  Listen: http://{address}:{port}',
		f'  Handlers: {len(routes)} handlers',
	]
	for route in routes:
		lines.extend((
			f'    - {route.object.properties.name if route.object.properties.name is not None else route.object.__qualname__}',
			f'      {route.method} {route.url}',
		))
	if server.app.exts:
		lines.append(f'  Extensions: {len(server.app.exts)} extensions')
		for extension in server.app.exts.values():
			lines.append(
				f'    - {type(extension).__name__}: {extension.path}',
			)
	lines.append('\n')
	text = '\n'.join(lines)
	encoding = getattr(sys.stdout, 'encoding', None)
	if encoding is not None:
		# Escape only unencodable characters to preserve startup information.
		text = text.encode(encoding, errors='backslashreplace').decode(encoding)
	print(
		text,
		flush=True,
	)
	return
