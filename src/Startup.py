from os import environ
import sys
from .Application import Application

__all__ = (
	'LOGO',
	'supports_color',
	'colorize_logo',
	'startup',
)


# Coder Mini Style
# https://patorjk.com/software/taag/#p=display&f=Coder+Mini&t=DefChord&x=none&v=4&h=4&w=80&we=false
LOGO = r"""
▄▄▄▄▄▄           ▄▄  ▄▄▄▄▄▄▄ ▄▄                   ▄▄
███▀▀██▄        ██  ███▀▀▀▀▀ ██                   ██
███  ███ ▄█▀█▄ ▀██▀ ███      ████▄ ▄███▄ ████▄ ▄████
███  ███ ██▄█▀  ██  ███      ██ ██ ██ ██ ██ ▀▀ ██ ██
██████▀  ▀█▄▄▄  ██  ▀███████ ██ ██ ▀███▀ ██    ▀████

Just def. Define your code. Compose your chord. You don't need to await this.
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


def startup(
	application: Application,
	server: str,
	host: str,
	port: int,
) -> None:
	"""Log the application's registration details, adapter name, and listening address."""
	if not isinstance(host, str):
		raise TypeError('HTTP listen address must be a string')
	address = f'[{host}]' if ':' in host else host
	logo = LOGO.rstrip()
	starting = 'Starting'
	if supports_color():
		logo = colorize_logo(logo)
		starting = f'\033[1;38;5;51m{starting}\033[0m'
	routes = [
		route for route in application.router.routes
		if route not in application.extension_routes
	]
	lines = [
		logo,
		'',
		starting,
		f'  Server: {server}',
		f'  Listen: http://{address}:{port}',
		f'  Applications: {len(routes)} applications',
	]
	for route in routes:
		lines.extend((
			f'    - {route.object.properties.name if route.object.properties.name is not None else route.object.__qualname__}',
			f'      {route.method} {route.url}',
		))
	if application.exts:
		lines.append(f'  Extensions: {len(application.exts)} extensions')
		for extension in application.exts:
			lines.append(
				f'    - {extension}',
			)
	lines.append('\n')
	text = '\n'.join(lines)
	encoding = getattr(sys.stdout, 'encoding', None)
	if encoding is not None:
		# Escape only unprintable characters to preserve the startup details.
		text = text.encode(encoding, errors='backslashreplace').decode(encoding)
	print(
		text,
		flush=True,
	)
	return
