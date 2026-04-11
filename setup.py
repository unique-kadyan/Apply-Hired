import os
import subprocess

from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install


def _build_frontend():
    cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
    subprocess.check_call(['npm', 'ci'], cwd=cwd)
    subprocess.check_call(['npm', 'run', 'build'], cwd=cwd)


class _Develop(develop):
    def run(self):
        develop.run(self)
        _build_frontend()


class _Install(install):
    def run(self):
        install.run(self)
        _build_frontend()


setup(
    name='apply-hired',
    version='0.1.0',
    packages=[],
    cmdclass={'develop': _Develop, 'install': _Install},
)
