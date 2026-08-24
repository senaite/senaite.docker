#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

from setuptools import find_packages
from setuptools import setup


setup(
    name="maitux.hazardcategories",
    version="0.1.0",
    description="Editable hazard categories for SENAITE",
    long_description=open("README.rst").read() if os.path.exists("README.rst") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://github.com/maitux/maitux.hazardcategories",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    package_data={
        "maitux.hazardcategories": [
            "*.zcml",
            "browser/*.zcml",
            "profiles/default/*.xml",
            "profiles/default/*.txt",
            "profiles/uninstall/*.xml",
            "profiles/uninstall/*.txt",
        ]
    },
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "senaite.lims",
        "plone.api",
        "plone.app.registry",
        "plone.supermodel",
        "zope.component",
        "zope.interface",
        "zope.processlifetime",
        "Products.CMFPlone",
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)
