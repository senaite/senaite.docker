from setuptools import setup, find_packages

setup(
    name="maitux.projects",
    version="1.0.0",
    description="Project Management for INNOCARE (仿 SENAITE Batches)",
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
