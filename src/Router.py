from typing import (
	Dict,
	Tuple,
)

from .Route import Route


class Router:
	"""Maintain per-Application registrations and prioritize static routes."""

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
				raise ValueError('Route already registered: {} {}'.format(
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
