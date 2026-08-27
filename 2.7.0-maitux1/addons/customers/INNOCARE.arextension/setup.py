import os
from setuptools import find_packages
from setuptools import setup

setup(
    name="INNOCARE.arextension",
    version="1.0.0",
    description="Analysis Request Custom Extensions for INNOCARE",
    long_description="",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://example.invalid/INNOCARE.arextension",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["INNOCARE"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "archetypes.schemaextender",
        "zope.interface",
    ],
)
