from html import escape
from importlib.resources import files
from re import sub
from typing import Optional

from ...Response import Response

__all__ = (
	'page',
)


def page(
	name: str,
	title: str,
	description: str,
	*,
	parameters: Optional[dict[str, str]] = None,
	policy: Optional[str] = None,
) -> Response:
	values = {
		'title': escape(title),
		'description': escape(description),
	}
	if parameters is not None:
		values.update({key: escape(value) for key, value in parameters.items()})
	text = files(__name__.rpartition('.')[0]).joinpath(name + '.html').read_text(encoding='utf-8')
	text = sub(
		r'\{\{(' + '|'.join(values) + r')\}\}',
		lambda match: values[match[1]],
		text,
	)
	return Response(
		body=text.encode('utf-8'),
		format='text/html',
		charset='utf-8',
		headers={
			'Content-Security-Policy': policy if policy is not None else "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
			'X-Content-Type-Options': 'nosniff',
			'Referrer-Policy': 'no-referrer',
			'Cache-Control': 'no-store',
		},
	)
