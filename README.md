Rig
===

![The Rig Logo](docs/source/logo.png?raw=true)

[![Build Status](https://travis-ci.org/project-rig/rig.svg?branch=master)](https://travis-ci.org/project-rig/rig)
[![PyPi version](https://pypip.in/v/rig/badge.png?style=flat)](https://pypi.python.org/pypi/rig/)
[![Documentation](https://readthedocs.org/projects/rig/badge/?version=master)](http://rig.readthedocs.org/)
[![Coverage Status](https://coveralls.io/repos/project-rig/rig/badge.svg?branch=master)](https://coveralls.io/r/project-rig/rig?branch=master)

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

Rig also provides a handful of simple commandline tools which may be useful:

`rig-boot`
    Boots a SpiNNaker board.
`rig-power`
    Power on/off SpiNNaker boards (via their BMP).
`rig-info`
    Print basic SpiNNaker/BMP status information (e.g. working cores, running
    applications, temperature).

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

    git clone git@github.com:project-rig/rig.git
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

This runs a subset of the full test suite which does not require any additional
hardware.

### Running tests against real hardware

Some tests require a connected SpiNNaker system. To run these use:

    py.test --spinnaker SPINN_HOSTNAME WIDTH HEIGHT

Though the vast majority of tests will run against any SpiNNaker system with at
least 4x4 working chips, the complete test suite should run against a single
SpiNN-5 board. To enable these additional tests, add the `--spinn5` argument:

    py.test --spinnaker SPINN_HOSTNAME 8 8 --spinn5

Other tests require a connected BMP (Board Management Processor, part of
SpiNN-5 boards). To run these use:

    py.test --bmp BMP_HOSTNAME

When a BMP is connected, the test suite will attempt to power-cycle the
attached board. When a SpiNNaker system is connected, the test suite will
attempt to boot the system.

To skip the power-cycling and booting tests, simply add the `--no-boot`
argument.

### Running tests against remote hardware

Booting a SpiNNaker board requires the (reliable) sending of packets to UDP
port 54321 which is frequently blocked by ISPs and is not reliable (since UDP
gives no guarantees, especially on the open internet). As a result, a proxy
server must be used to communicate with the board. A utility such as
[`spinnaker_proxy`](https://github.com/project-rig/spinnaker_proxy) can be used
alongside the test suite as follows:

    # On the test machine
    spinnaker_proxy.py -ctq PROXY_SERVER_HOSTNAME &
    PROXY_PID=$!
    py.test --proxy --spinnaker localhost WIDTH HEIGHT --bmp BMP_HOSTNAME
    kill $PROXY_PID
    
    # On a machine on the same LAN as the spinnaker machine
    spinnaker_proxy.py -stq SPINN_HOSTNAME

We use this configuration to enable remote Travis-CI test runs to drive
SpiNNaker hardware in Manchester.

### Test coverage checking

To get a test coverage report run one of the following:

    # Summary (for rig module)
    py.test --cov rig
    
    # List missed line numbers (for rig module)
    py.test --cov rig --cov-report term-missing
    
    # Generate HTML report (for rig module)
    py.test --cov rig --cov-report html


### Code standards checking

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

The ReadTheDocs project page is available here: https://readthedocs.org/projects/rig/
