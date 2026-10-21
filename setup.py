# -*- coding: utf-8 -*-

from pathlib import Path

from setuptools import (
	find_packages,
	setup,
)

PACKAGE = 'DefStar'
SOURCE = 'src'
PACKAGES = [PACKAGE]
PACKAGE_DIR = {PACKAGE: SOURCE}

for package in find_packages(SOURCE):
	PACKAGES.append('{}.{}'.format(PACKAGE, package))
	PACKAGE_DIR['{}.{}'.format(PACKAGE, package)] = '{}/{}'.format(
		SOURCE,
		package.replace('.', '/'),
	)

setup(
	name='DefStar',
	description='The Modern Synchronous Python WSGI Framework',
	long_description=Path('README.md').read_text(encoding='utf-8'),
	long_description_content_type='text/markdown',
	author='Heo Yongseon',
	url='https://github.com/yong5eon/DefStar',
	project_urls={
		'Source': 'https://github.com/yong5eon/DefStar',
		'Issues': 'https://github.com/yong5eon/DefStar/issues',
		'Releases': 'https://github.com/yong5eon/DefStar/releases',
	},
	use_scm_version={
		'tag_regex': r'^v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:rc|\.post)[0-9]+)?)$',
	},
	setup_requires=[
		'setuptools-scm>=8,<10',
	],
	packages=PACKAGES,
	package_dir=PACKAGE_DIR,
	include_package_data=False,
	package_data={
		'DefStar.Extensions': [
			'Dashboard.html',
			'Swagger.html',
		],
	},
	classifiers=[
		'Programming Language :: Python :: 3.9',
		'Programming Language :: Python :: 3.10',
		'Programming Language :: Python :: 3.11',
		'Programming Language :: Python :: 3.12',
		'Programming Language :: Python :: 3.13',
		'Programming Language :: Python :: 3.14',
	],
	extras_require={
	},
	python_requires='>=3.9',
)
