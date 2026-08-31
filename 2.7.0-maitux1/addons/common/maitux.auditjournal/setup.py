# -*- coding: utf-8 -*-
import os

from setuptools import find_packages, setup


setup(
    name="maitux.auditjournal",
    version="1.0.0",
    description="Audit journal index for SENAITE (PostgreSQL)",
    long_description=open("README.rst").read() if os.path.exists("README.rst") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://github.com/maitux/maitux.auditjournal",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    package_data={
        "maitux.auditjournal": [
            "*.zcml",
            "profiles/default/*.xml",
            "upgrades/*.zcml",
            "browser/*.zcml",
            "browser/templates/*.pt",
            "locales/*/LC_MESSAGES/*.po",
            "locales/*/LC_MESSAGES/*.mo",
        ]
    },
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "senaite.lims",
        # psycopg2 由 RelStorage 带入（容器内 2.8.6，实测可用），
        # 容器无外网、装不上新依赖，所以这里不声明也不升级它。
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
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
