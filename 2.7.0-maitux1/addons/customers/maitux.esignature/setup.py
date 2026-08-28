import os
from setuptools import find_packages, setup


setup(
    name="maitux.esignature",
    version="0.2.1",
    description="MAITUX electronic signature add-on",
    long_description=open("README.rst").read() if os.path.exists("README.rst") else "",
    author="MAITUX Team",
    author_email="dev@maitux.com",
    url="",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux", "medai", "medai.senaite"],
    include_package_data=True,
    package_data={
        "maitux.esignature": [
            "*.zcml",
            "browser/templates/*.pt",
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
        "zope.interface",
        "zope.component",
        "persistent",
        "BTrees",
        "zope.annotation",
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
