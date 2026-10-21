from typing import (
	Dict,
	Tuple,
)

from .Route import Route


class Router:
	"""Application별 등록 상태와 정적 경로 우선순위를 유지한다."""

	def __init__(self):
		self.routes: list[Route] = []
		return

	def add(
		self,
		route: Route,
	) -> None:
		for registered in self.routes:
			if registered.method == route.method and registered.url == route.url:
				if registered.object is route.object:
					return
				raise ValueError('이미 등록된 라우트: {} {}'.format(
					route.method,
					route.url,
				))
		self.routes.append(route)
		self.routes.sort(key=lambda entry: entry.priority)
		return

	def matches(
		self,
		url: str,
	) -> Dict[str, Tuple[Route, dict[str, str]]]:
		matches = {}
		for route in self.routes:
			parameters = route.match(url)
			if parameters is not None and route.method not in matches:
				matches[route.method] = (
					route,
					parameters,
				)
		return matches
