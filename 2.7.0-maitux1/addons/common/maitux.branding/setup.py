import os
from setuptools import find_packages, setup


setup(
    name="maitux.branding",
    version="0.1.0",
    description="Maitux branding add-on for SENAITE",
    long_description=open("README.rst").read() if os.path.exists("README.rst") else "",
    author="Maitux Team",
    author_email="dev@maitux.com",
    url="https://github.com/maitux/maitux.branding",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    package_data={
        "maitux.branding": [
            "*.zcml",
            "browser/*.zcml",
            "browser/templates/*.pt",
            "profiles/default/*.xml",
            "profiles/default/*.txt",
            "profiles/default/*.py",
            "profiles/default/resources/*.png",
            "profiles/uninstall/*.xml",
            "profiles/uninstall/*.txt",
        ]
    },
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "senaite.lims",
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
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)

