import os
import sys
from setuptools import setup

# Avoid polluting the .tar.gz with ._* files under Mac OS X
os.putenv('COPYFILE_DISABLE', 'true')

root = os.path.dirname(__file__)

description = "An implementation of the WebSocket Protocol (RFC 6455)"

with open(os.path.join(root, 'README.rst'), encoding='utf-8') as f:
    long_description = '\n\n'.join(f.read().split('\n\n')[1:])

with open(os.path.join(root, 'websockets', 'version.py'),
          encoding='utf-8') as f:
    exec(f.read())

if sys.version_info < (3, 3):
    raise Exception("websockets requires Python >= 3.3.")

setup(
    name='websockets',
    version=version,  # noqa
    author='Aymeric Augustin',
    author_email='aymeric.augustin@m4x.org',
    url='https://github.com/aaugustin/websockets',
    description=description,
    long_description=long_description,
    download_url='https://pypi.python.org/pypi/websockets',
    packages=[
        'websockets',
    ],
    extras_require={':python_version=="3.3"': ['asyncio']},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.3",
    ],
    platforms='all',
    license='BSD'
)
