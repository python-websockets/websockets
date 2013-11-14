import os
import sys
import setuptools

# Avoid polluting the .tar.gz with ._* files under Mac OS X
os.putenv('COPYFILE_DISABLE', 'true')

root = os.path.dirname(__file__)

# Prevent distutils from complaining that a standard file wasn't found
README = os.path.join(root, 'README')
if not os.path.exists(README):
    os.symlink(README + '.rst', README)

description = "An implementation of the WebSocket Protocol (RFC 6455)"

with open(os.path.join(root, 'README')) as f:
    long_description = '\n\n'.join(f.read().split('\n\n')[1:])

with open(os.path.join(root, 'websockets', 'version.py')) as f:
    exec(f.read())

py_version = sys.version_info[:2]

if py_version < (3, 3):
    raise Exception("websockets requires Python >= 3.3.")

setuptools.setup(
    name='websockets',
    version=version,
    author='Aymeric Augustin',
    author_email='aymeric.augustin@m4x.org',
    url='https://github.com/aaugustin/websockets',
    description=description,
    long_description=long_description,
    download_url='https://pypi.python.org/pypi/websockets',
    packages=[
        'websockets',
    ],
    install_requires=['asyncio'] if py_version == (3, 3) else [],
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
