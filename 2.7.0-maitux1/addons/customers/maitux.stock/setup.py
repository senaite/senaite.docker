from setuptools import setup, find_packages

setup(
    name='maitux.stock',
    version='1.0.0',
    description="Stock Management for MAITUX",
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
