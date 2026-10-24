from ...Extension import Extension
from ...Route import Route
from ...Runners.RunExtension import RunExtensionFactory

__all__ = (
	'validate_path',
	'http_routes',
)


def validate_path(path: str) -> None:
	if not isinstance(path, str) or not path.startswith('/') or any(
		character in path for character in (
			'?',
			'#',
			':',
		)
	):
		raise ValueError('Extensions require an absolute HTTP path without parameters')
	return


def http_routes(
	extension: Extension,
	path: str,
) -> tuple[Route, ...]:
	"""확장에 GET 및 HEAD 요청 실행기를 연결한다."""
	return tuple(
		Route(
			method,
			path,
			RunExtensionFactory(
				extension,
				method,
				path,
			)(),
		)
		for method in (
			'GET',
			'HEAD',
		)
	)
