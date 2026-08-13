# -*- coding: utf-8 -*-
import os

from setuptools import find_packages
from setuptools import setup


setup(
    name="maitux.oauth2",
    version="0.1.0",
    description="Bamboocloud (BCastle) IDaaS OAuth 2.0 single sign-on for SENAITE",
    long_description=open("README.rst").read() if os.path.exists("README.rst") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://github.com/maitux/maitux.oauth2",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    package_data={
        "maitux.oauth2": [
            "*.zcml",
            "browser/*.zcml",
            "browser/templates/*.pt",
            "profiles/default/*.xml",
            "profiles/default/*.txt",
            "profiles/uninstall/*.xml",
            "profiles/uninstall/*.txt",
        ]
    },
    zip_safe=False,
    # NOTE: deliberately no `requests` here -- the HTTP client is built on the
    # standard library so that adding this add-on cannot drag new pins into the
    # (very tightly pinned) Python 2.7 buildout.
    install_requires=[
        "setuptools",
        "six",
        "senaite.core",
        "senaite.lims",
        "plone.api",
        "plone.app.registry",
        "plone.supermodel",
        "zope.component",
        "zope.interface",
    ],
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
        "Programming Language :: Python :: 2.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
