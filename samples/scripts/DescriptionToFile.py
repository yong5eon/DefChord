from argparse import ArgumentParser
from json import dumps
from pathlib import Path

from DefChord.Extensions import Specifications
from ..Sample import create_application


def main() -> None:
	"""Save the OpenAPI document from the started sample app and clean up its resources."""
	parser = ArgumentParser(description='샘플 OpenAPI 문서 생성')
	parser.add_argument(
		'output',
		type=Path,
	)
	args = parser.parse_args()
	app = create_application()
	spec = next(extension for extension in app.exts if isinstance(extension, Specifications))
	app.start()
	try:
		args.output.write_text(
			dumps(
				spec.document(),
				ensure_ascii=False,
				indent=2,
				allow_nan=False,
			) + '\n',
			encoding='utf-8',
		)
	finally:
		app.stop()
	return


if __name__ == '__main__':
	main()
