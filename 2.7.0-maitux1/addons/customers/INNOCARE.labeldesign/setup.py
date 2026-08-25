#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

from setuptools import find_packages
from setuptools import setup


setup(
    name="maitux.labeldesign",
    version="0.1.0",
    description="INNOCARE label/sticker designs for A4/Label printers",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://github.com/maitux/maitux.labeldesign",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    package_data={
        "maitux.labeldesign": [
            "*.zcml",
            "browser/*.zcml",
            "browser/stickers/*.zcml",
            "browser/stickers/templates/stockbatch/*.pt",
            "browser/stickers/templates/stockbatch/*.css",
            "browser/stickers/templates/sample/*.pt",
            "browser/stickers/templates/sample/*.css",
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
        "bika.lims",
        "maitux.stock",
        "INNOCARE.arextension",
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)