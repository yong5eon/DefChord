from argparse import ArgumentParser
from json import dumps
from pathlib import Path

from DefEssential.Extensions import Specifications
from ..Sample import create_application


def main() -> None:
	"""시작한 샘플 앱의 OpenAPI 문서를 저장하고 자원을 정리한다."""
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
