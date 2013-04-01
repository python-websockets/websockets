import distutils.core
import os

# Avoid polluting the .tar.gz with ._* files under Mac OS X
os.putenv('COPYFILE_DISABLE', 'true')

description = "An implementation of the WebSocket Protocol (RFC 6455)"

with open(os.path.join(os.path.dirname(__file__), 'README')) as f:
    long_description = '\n\n'.join(f.read().split('\n\n')[1:])

distutils.core.setup(
    name='websockets',
    version='0.1',
    author='Aymeric Augustin',
    author_email='aymeric.augustin@m4x.org',
    url='https://github.com/aaugustin/websockets',
    description=description,
    long_description=long_description,
    download_url='https://pypi.python.org/pypi/websockets',
    packages=[
        'websockets',
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
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
