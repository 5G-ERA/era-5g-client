python_sources(
    name="lib",
    skip_mypy=True,
    skip_black=True,
    skip_flake8=True,
)

# this is to force flake8/mypy to test with different versions of Python
python_sources(name="lib_py38", interpreter_constraints=["==3.8.*"])
python_sources(name="lib_py39", interpreter_constraints=["==3.9.*"])
python_sources(name="lib_py310", interpreter_constraints=["==3.10.*"])

resources(name="py.typed", sources=["py.typed"])

python_distribution(
    name="dist",
    dependencies=[":lib", ":py.typed"],
    wheel=True,
    sdist=True,
    provides=setup_py(
        name="era_5g_client",
        version="0.2.0",
        description="A client for 5G-ERA NetApps",
        author="Michal Kapinus",
        author_email="ikapinus@fit.vutbr.cz",
        license="LGPL",
        python_requires=">=3.8,<3.11",
        classifiers=[
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
            "Operating System :: OS Independent",
            "Intended Audience :: Developers",
        ],
    ),
)
