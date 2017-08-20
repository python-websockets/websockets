import os.path
import sys

import setuptools

root_dir = os.path.abspath(os.path.dirname(__file__))

description = "An implementation of the WebSocket Protocol (RFC 6455)"

readme_file = os.path.join(root_dir, 'README.rst')
with open(readme_file, encoding='utf-8') as f:
    long_description = f.read()

version_module = os.path.join(root_dir, 'websockets', 'version.py')
with open(version_module, encoding='utf-8') as f:
    exec(f.read())

py_version = sys.version_info[:2]

if py_version < (3, 3):
    raise Exception("websockets requires Python >= 3.3.")

packages = ['websockets']

if py_version >= (3, 5):
    packages.append('websockets/py35')

ext_modules = [
    setuptools.Extension(
        'websockets.speedups',
        sources=['websockets/speedups.c'],
        optional=not os.path.exists(os.path.join(root_dir, '.cibuildwheel')),
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
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    packages=packages,
    ext_modules=ext_modules,
    extras_require={
        ':python_version=="3.3"': ['asyncio'],
    },
)
