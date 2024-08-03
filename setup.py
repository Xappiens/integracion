from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# Obtener la versión de __version__ variable en integracion/__init__.py
from integracion import __version__ as version

setup(
    name="integracion",
    version=version,
    description="Integración",
    author="Xappiens",
    author_email="info@xappiens.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
