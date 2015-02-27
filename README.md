Rig
===

![The Rig Logo](docs/source/logo.png?raw=true)

[![Build Status](https://travis-ci.org/project-rig/rig.svg?branch=master)](https://travis-ci.org/project-rig/rig)
[![PyPi version](https://pypip.in/v/rig/badge.png)](https://pypi.python.org/pypi/rig/)
[![Documentation Status](https://readthedocs.org/projects/rig/badge/?version=master)](https://readthedocs.org/projects/rig/?badge=master)

Rig is a set of Python and C libraries for mapping computational problems to
SpiNNaker and interacting with them.  Above all it aims to be light weight and
to present common and well-documented interfaces to all of its parts.

Overview
--------

Rig is split into three primary groups of tools and utilities:

### Execution specification

Allows specification of the sets of executables that are to be simulated on
SpiNNaker.  Tools exist for:

 - Specifying regions of memory.
 - Generating "keyspaces" for routing multicast packets.
 - Converting from Numpy arrays and floats to fix-point values and vice-versa.
 - Specifying a problem for SpiNNaker in terms of computational nodes and their
   communication.

### Problem mapping

 - Placing: Taking a set of computational nodes and determining which SpiNNaker
   processing cores they should be placed on.
 - Routing: Taking a set of computational nodes and determining the routing
   entries necessary to fulfil their communication needs.

### Execution control

 - A light-weight SCP interface to load applications and data onto a SpiNNaker
   machine and to control their execution.

### Related projects

 - Clock discipline
 - Routing table minimisation
 - Optimal routing key allocation

Using Rig
---------

Users can install Rig from the [Python Package
Index](https://pypi.python.org/pypi/rig/) using:

    pip install rig

Documentation is available online on [ReadTheDocs](http://rig.readthedocs.org/).

Developing Rig
--------------

Users wishing to work on Rig can download the latest code from the [official
GitHub repository](https://github.com/project-rig/rig).

### `virtualenv` setup

We recommend working in a [virtualenv](https://pypi.python.org/pypi/virtualenv)
which can be set up like so:

    # `--system-site-packages` optionally allows the virtualenv to use your
    # system-wide installations of large packages (e.g. NUMPY)
    virtualenv --system-site-packages rig_virtualenv
    cd rig_virtualenv
    . bin/activate

This will install the requirements and provide you with a sandboxed environment
for testing and working with rig.  To leave the `virtualenv` just run
`deactivate`. Run `. bin/activate` whenever you want to re-enter the
environment.

### Installing Rig

A development installation of rig can be created straight out of the repository
using [setuptools](https://pypi.python.org/pypi/setuptools) as usual:

    git clone git@github.com:mundya/rig
    cd rig
    python setup.py develop

### Running tests

We use [py.test](http://pytest.org) to test rig,
[pytest-cov](https://pypi.python.org/pypi/pytest-cov/1.8.1) to generate coverage
reports and the [flake8](https://pypi.python.org/pypi/flake8) coding standard
checker. Developers should be careful to test for compliance before pushing
code.

The required tools can be installed via pip using:

    pip install -r requirements-test.txt

The tests can now be run using:

    py.test

Some tests require a connected, non-booted, SpiNNaker system.  To run these use:

    py.test --spinnaker HOSTNAME WIDTH HEIGHT

To get a test coverage report run one of the following:

    # Summary (for rig module)
    py.test --cov rig
    
    # List missed line numbers (for rig module)
    py.test --cov rig --cov-report term-missing
    
    # Generate HTML report (for rig module)
    py.test --cov rig --cov-report html

To test for coding standards problems run:

    flake8 rig

### Using Tox

We also use [Tox](https://pypi.python.org/pypi/tox/1.8.1) to run tests against
multiple versions of Python. To do this just execute `tox` in the root
directory of the repository.


### Building documentation

Documentation is built by
[Sphinx](http://sphinx-doc.org/)/[numpydoc](https://github.com/numpy/numpydoc).
Dependencies can be installed using:

    pip install -r requirements-docs.txt

HTML documentation can be built using:

    cd docs
    make html

HTML documentation is created in `docs/build/html/`.

Note: `virtualenv` users using `--system-site-packages` and who have a system-wide
installed version of sphinx may find that the build process fails. To install a
local copy of Sphinx in the `virtualenv`, use:

    pip install -I sphinx
