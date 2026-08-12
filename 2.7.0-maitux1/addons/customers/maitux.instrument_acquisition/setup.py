from setuptools import find_packages
from setuptools import setup


setup(
    name="maitux.instrument_acquisition",
    version="1.0.0",
    description="Instrument Acquisition for MAITUX",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "requests",
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)

