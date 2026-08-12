# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name='maitux.testmodel',
    version='1.0.0',
    description="Maitux Testmodel Add-on for SENAITE",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=['maitux'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'setuptools',
        'senaite.core',
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)
