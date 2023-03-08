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

pex_binary(
    name="client_gstreamer",
    entry_point="client_gstreamer.py",
)

pex_binary(
    name="client_http",
    entry_point="client_http_no_middleware.py",
)
