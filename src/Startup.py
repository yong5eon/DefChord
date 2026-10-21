from os import (
	environ,
	getpid,
)
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .Server import Server


LOGO = r"""
▄▄▄▄▄▄           ▄▄  ▄▄▄▄▄▄▄
███▀▀██▄        ██  █████▀▀▀  ██
███  ███ ▄█▀█▄ ▀██▀  ▀████▄  ▀██▀▀  ▀▀█▄ ████▄
███  ███ ██▄█▀  ██     ▀████  ██   ▄█▀██ ██ ▀▀
██████▀  ▀█▄▄▄  ██  ███████▀  ██   ▀█▄██ ██

Just def. Let web applications do the work. You don't need to await this.
"""


def supports_color() -> bool:
	"""터미널 출력에서만 색상을 사용하고 NO_COLOR 설정을 우선한다."""
	return (
		getattr(sys.stdout, 'isatty', lambda: False)()
		and 'NO_COLOR' not in environ
	)


def colorize_logo(logo: str) -> str:
	"""배너의 다섯 줄에 기존 Startup의 색상 그라데이션을 적용한다."""
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
	"""바인딩된 서버와 Application의 실제 등록 상태를 출력한다."""
	host, port = server.server_address[:2]
	if not isinstance(host, str):
		raise TypeError('HTTP 수신 주소는 문자열이어야 합니다')
	address = f'[{host}]' if ':' in host else host
	logo = LOGO.rstrip()
	starting = 'Starting Application'
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
			f'    - {route.object.__qualname__}',
			f'      {route.method} {route.url}',
		))
	if server.app.exts:
		lines.append(f'  Extensions: {len(server.app.exts)} extensions')
		for extension in server.app.exts.values():
			lines.append(
				f'    - {type(extension).__name__}: http://{address}:{port}{extension.path}',
			)
	lines.append('\n')
	text = '\n'.join(lines)
	encoding = getattr(sys.stdout, 'encoding', None)
	if encoding is not None:
		# 출력 인코딩에서 표현할 수 없는 문자만 이스케이프해 실행 정보를 보존한다.
		text = text.encode(encoding, errors='backslashreplace').decode(encoding)
	print(
		text,
		flush=True,
	)
	return
