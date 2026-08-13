from setuptools import find_packages
from setuptools import setup


setup(
    name="maitux.stability",
    version="1.0.0",
    description="Stability Studies for MAITUX",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["maitux"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "setuptools",
        "senaite.core",
        "maitux.stock",
    ],
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    """,
)
