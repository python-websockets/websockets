import os.path
import sys
import warnings
import platform

import setuptools
from distutils.core import Extension

# The following code is copied from
# https://github.com/mongodb/mongo-python-driver/blob/master/setup.py
# to support installing without the extension on platforms where
# no compiler is available.
from distutils.command.build_ext import build_ext


class custom_build_ext(build_ext):
    """Allow C extension building to fail.
    The C extension speeds up websocket masking, but is not essential.
    """

    warning_message = """
********************************************************************
WARNING: %s could not
be compiled. No C extensions are essential for websockets to run,
although they do result in significant speed improvements for
websockets.
%s
Here are some hints for popular operating systems:
If you are seeing this message on Linux you probably need to
install GCC and/or the Python development package for your
version of Python.
Debian and Ubuntu users should issue the following command:
    $ sudo apt-get install build-essential python-dev
RedHat and CentOS users should issue the following command:
    $ sudo yum install gcc python-devel
Fedora users should issue the following command:
    $ sudo dnf install gcc python-devel
If you are seeing this message on OSX please read the documentation
here:
http://api.mongodb.org/python/current/installation.html#osx
********************************************************************
"""

    def run(self):
        try:
            build_ext.run(self)
        except Exception:
            e = sys.exc_info()[1]
            sys.stdout.write('%s\n' % str(e))
            warnings.warn(self.warning_message % ("Extension modules",
                                                  "There was an issue with "
                                                  "your platform configuration"
                                                  " - see above."))

    def build_extension(self, ext):
        name = ext.name
        try:
            build_ext.build_extension(self, ext)
        except Exception:
            e = sys.exc_info()[1]
            sys.stdout.write('%s\n' % str(e))
            warnings.warn(self.warning_message % ("The %s extension "
                                                  "module" % (name,),
                                                  "The output above "
                                                  "this warning shows how "
                                                  "the compilation "
                                                  "failed."))


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

kwargs = {}
if (platform.python_implementation() == 'CPython' and
        os.environ.get('WEBSOCKETS_EXTENSION') != '0'):
    # This extension builds and works on pypy as well, although pypy's jit
    # produces equivalent performance.
    kwargs['ext_modules'] = [
        Extension('websockets.speedups',
                  sources=['websockets/speedups.c']),
    ]

    if os.environ.get('WEBSOCKETS_EXTENSION') != '1':
        # Unless the user has specified that the extension is mandatory,
        # fall back to the pure-python implementation on any build failure.
        kwargs['cmdclass'] = {'build_ext': custom_build_ext}

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
    ],
    packages=packages,
    extras_require={
        ':python_version=="3.3"': ['asyncio'],
    },
    **kwargs
)
