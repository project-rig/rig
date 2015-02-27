# Rig

[![Build Status](https://travis-ci.org/project-rig/rig.svg?branch=master)](https://travis-ci.org/project-rig/rig)
[![PyPi version](https://pypip.in/v/rig/badge.png)](https://pypi.python.org/pypi/rig/)
[![Documentation Status](https://readthedocs.org/projects/rig/badge/?version=master)](https://readthedocs.org/projects/rig/?badge=master)

Rig is a set of Python and C libraries for mapping computational problems to
SpiNNaker and interacting with them.  Above all it aims to be light weight and
to present common and well-documented interfaces to all of its parts.

Rig is split into three primary groups of tools and utilities:

## Execution specification

Allows specification of the sets of executables that are to be simulated on
SpiNNaker.  Tools exist for:

 - Specifying regions of memory.
 - Generating "keyspaces" for routing multicast packets.
 - Converting from Numpy arrays and floats to fix-point values and vice-versa.
 - Specifying a problem for SpiNNaker in terms of computational nodes and their
   communication.

## Problem mapping

 - Placing: Taking a set of computational nodes and determining which SpiNNaker
   processing cores they should be placed on.
 - Routing: Taking a set of computational nodes and determining the routing
   entries necessary to fulfil their communication needs.

## Execution control

 - A light-weight SCP interface to load applications and data onto a SpiNNaker
   machine and to control their execution.

## Related projects

 - Clock discipline
 - Routing table minimisation
 - Optimal routing key allocation

## Developing Rig

### Installing in a `virtualenv`

Create a new [virtualenv](https://pypi.python.org/pypi/virtualenv) by running:

    virtualenv --system-site-packages new_directory_name

Note `--system-site-packages` optionally allows the virtualenv to use your
system-wide installations of large packages (e.g. NUMPY)

Then activate the virtualenv before installing.

    cd new_directory_name
    . bin/activate

Clone and install.

    git clone git@github.com:mundya/rig
    cd rig
    python setup.py install develop

This will install the requirements and provide you with a sandboxed environment
for testing and working with rig.  To leave the virtualenv just run
`deactivate`.  Run `. bin/activate` whenever you want to re-enter the
environment.

### Running the tests

We use [py.test](http://pytest.org) to test rig,
[pytest-cov](https://pypi.python.org/pypi/pytest-cov/1.8.1) to generate
coverage reports and the [flake8](https://pypi.python.org/pypi/flake8) coding
standard checker.

Install py.test et al. in the virtualenv.

    pip install pytest pytest-cov flake8 mock

*To run the tests*:

(You must be in the rig module directory, e.g. `new_directory_name/rig/rig/`)

    py.test

To run the tests and get a coverage report.

    py.test --cov rig

To run the tests and get a specific coverage report (with line numbers):

    py.test --cov rig --cov-report term-missing

Some tests require a connected, booted, SpiNNaker board.  To run these use:

    py.test --spinnaker=HOSTNAME_OF_BOOTED_BOARD

#### Using Tox

We also use [Tox](https://pypi.python.org/pypi/tox/1.8.1) to run tests against
multiple versions of Python.  To do this just execute `tox` in the root
directory of the repository.


# Documentation

The Rig documentation is hosted at: http://rig.readthedocs.org/
