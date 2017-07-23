import glob
import os.path
import platform
import setuptools
import sys
from distutils import log
from distutils.cmd import Command
from distutils.core import Extension


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
    Extension(
        'websockets.speedups',
        sources=['websockets/speedups.c'],
        optional=True,
    ),
]

# Let's define a class to clean in-place built extensions
class CleanExtensionCommand(Command):
    """A custom command to clean all in-place built C extensions."""

    description = 'clean all in-place built C extensions'
    user_options = []

    def initialize_options(self):
        """Set default values for options."""

    def finalize_options(self):
        """Post-process options."""

    def run(self):
        """Run command."""
        for ext in ['*.so', '*.pyd']:
            for file in glob.glob('./websockets/' + ext):
                log.info("removing '%s'", file)
                if self.dry_run:
                    continue
                os.remove(file)

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
    cmdclass={
        'cleanext': CleanExtensionCommand,
    },
    extras_require={
        ':python_version=="3.3"': ['asyncio'],
    },
)
