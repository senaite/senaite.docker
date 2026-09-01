#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

from setuptools import find_packages
from setuptools import setup


setup(
    name="INNOCARE.LabelAndReport",
    version="1.0.0",
    description="Merged INNOCARE label and report templates add-on",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://example.invalid/INNOCARE.LabelAndReport",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["INNOCARE"],
    include_package_data=True,
    package_data={
        "INNOCARE.LabelAndReport": [
            "*.zcml",
            "profiles/default/*.xml",
            "profiles/default/*.txt",
            "profiles/uninstall/*.xml",
            "profiles/uninstall/*.txt",
        ],
        "INNOCARE.labeldesign": [
            "*.zcml",
            "browser/*.zcml",
            "browser/*.pt",
            "browser/stickers/*.zcml",
            "browser/stickers/templates/*.pt",
            "browser/stickers/templates/*.css",
        ],
        "INNOCARE.reportdesign": [
            "*.zcml",
            "templates/print/*.pt",
            "templates/print/*.css",
            "templates/reports/*.pt",
            "templates/reports/*.css",
        ],
    },
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "senaite.lims",
        "maitux.stock",
        "INNOCARE.arextension",
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)
