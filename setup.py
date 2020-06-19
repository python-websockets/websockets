import pathlib
import re
import sys

import setuptools

root_dir = pathlib.Path(__file__).parent

if sys.version_info[:3] < (3, 6, 1):
    raise Exception("websockets requires Python >= 3.6.1.")

ext_modules = [
    setuptools.Extension(
        'websockets.speedups',
        sources=['src/websockets/speedups.c'],
        optional=not (root_dir / '.cibuildwheel').exists(),
    )
]

setuptools.setup(ext_modules=ext_modules)
