# -*- coding: utf-8 -*-
from setuptools import find_packages
from setuptools import setup


setup(
    name="maitux.audittrail",
    version="1.0.0",
    description="Maitux audit trail readability add-on for SENAITE",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
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
