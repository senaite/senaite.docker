import os
from setuptools import setup, find_packages


setup(
    name="maitux.capabilityinventory",
    version="0.1.0",
    description="SENAITE Capability Inventory Export Module",
    long_description=open("README.rst").read() if os.path.exists("README.rst") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://github.com/maitux/maitux.capabilityinventory",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "senaite.lims",
        "plone.api",
        "zope.interface",
        "zope.component",
    ],
    extras_require={
        "test": [
            "plone.app.testing",
            "unittest2",
        ]
    },
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Plone",
        "Framework :: Plone :: 5.2",
        "Framework :: Zope2",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)

