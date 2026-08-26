import os
from setuptools import find_packages
from setuptools import setup

setup(
    name="INNOCARE.Reportdesign",
    version="1.0.0",
    description="Custom Worksheet Print Templates for INNOCARE (AS-grouped)",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://example.invalid/INNOCARE.Reportdesign",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["INNOCARE"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)
