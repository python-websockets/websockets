import pathlib
import sys

import setuptools


root_dir = pathlib.Path(__file__).parent

description = "An implementation of the WebSocket Protocol (RFC 6455 & 7692)"

# When dropping Python < 3.5, change to:
# long_description = (root_dir / 'README.rst').read_text(encoding='utf-8')
with (root_dir / 'README.rst').open(encoding='utf-8') as f:
    long_description = f.read()

# When dropping Python < 3.5, change to:
# exec((root_dir / 'websockets' / 'version.py').read_text(encoding='utf-8'))
with (root_dir / 'websockets' / 'version.py').open(encoding='utf-8') as f:
    exec(f.read())

py_version = sys.version_info[:2]

if py_version < (3, 4):
    raise Exception("websockets requires Python >= 3.4.")

packages = ['websockets', 'websockets/extensions']

if py_version >= (3, 5):
    packages.append('websockets/py35')

if py_version >= (3, 6):
    packages.append('websockets/py36')

ext_modules = [
    setuptools.Extension(
        'websockets.speedups',
        sources=['websockets/speedups.c'],
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
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    packages=packages,
    ext_modules=ext_modules,
    include_package_data=True,
    zip_safe=True,
    python_requires='>=3.4',
)
