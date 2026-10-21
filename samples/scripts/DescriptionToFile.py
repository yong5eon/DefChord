from argparse import ArgumentParser
from json import dumps
from pathlib import Path

from DefStar.Extensions import Spec
from ..Sample import create_application


def main() -> None:
	"""Save the sample Application's OpenAPI document to a file."""
	parser = ArgumentParser(description='Generate the sample OpenAPI document')
	parser.add_argument('output', type=Path)
	args = parser.parse_args()
	app = create_application()
	spec = next(extension for extension in app.exts.values() if isinstance(extension, Spec))
	args.output.write_text(
		dumps(
			spec.document(app),
			ensure_ascii=False,
			indent=2,
			allow_nan=False,
		) + '\n',
		encoding='utf-8',
	)
	return


if __name__ == '__main__':
	main()
