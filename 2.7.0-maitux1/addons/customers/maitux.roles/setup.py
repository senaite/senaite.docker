#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

from setuptools import find_packages
from setuptools import setup


setup(
    name="maitux.roles",
    version="0.1.0",
    description="Business roles, groups and accounts for SENAITE",
    long_description=open("README.rst").read() if os.path.exists("README.rst") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://github.com/maitux/maitux.roles",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    package_data={
        "maitux.roles": [
            "*.zcml",
            "profiles/default/*.xml",
        ]
    },
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "senaite.lims",
        "plone.api",
        "zope.processlifetime",
        "Products.CMFPlone",
        "INNOCARE.arextension",
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)
