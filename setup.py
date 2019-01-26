import pathlib
import sys

import setuptools


root_dir = pathlib.Path(__file__).parent

description = "An implementation of the WebSocket Protocol (RFC 6455 & 7692)"

long_description = (root_dir / 'README.rst').read_text(encoding='utf-8')

exec((root_dir / 'src' / 'websockets' / 'version.py').read_text(encoding='utf-8'))

py_version = sys.version_info[:2]

if py_version < (3, 6):
    raise Exception("websockets requires Python >= 3.6.")

packages = ['websockets', 'websockets/extensions']

ext_modules = [
    setuptools.Extension(
        'websockets.speedups',
        sources=['src/websockets/speedups.c'],
        optional=not (root_dir / '.cibuildwheel').exists(),
    )
]

setuptools.setup(
    name='websockets',
    version=version,
    description=description,
    long_description=long_description,
    url='https://github.com/aaugustin/websockets',
    author='Aymeric Augustin',
    author_email='aymeric.augustin@m4x.org',
    license='BSD',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    package_dir = {'': 'src'},
    packages=packages,
    ext_modules=ext_modules,
    include_package_data=True,
    zip_safe=True,
    python_requires='>=3.6',
    test_loader='unittest:TestLoader',
)
