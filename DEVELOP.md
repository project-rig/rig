Rig Development
===============

This document presents an overview of how to get up and running with a
development install of Rig and how it is tested, reviewed and released.

* [Developer Installation](#developer-installation)
* [Testing](#testing)
* [Documentation](#documentation)
* [Versioning and Releasing](#versioning-and-releasing)
* [Third-Party Services](#third-party-services)


Developer Installation
----------------------

By following the steps below, you can set up an appropriate environment for Rig
development.

### `virtualenv` setup (optional)

We recommend working in a [virtualenv](https://pypi.python.org/pypi/virtualenv)
which can be set up like so:

    # `--system-site-packages` optionally allows the virtualenv to use your
    # system-wide installations of large packages (e.g. NUMPY)
    virtualenv --system-site-packages rig_virtualenv
    cd rig_virtualenv
    . bin/activate

`virtualenv`s provide a (sort-of) standardised, sandboxed Python environment
for testing and working with rig. Run `. bin/activate` whenever you want to
re-enter the `virtualenv` environment in a new terminal. To leave the
`virtualenv` just run `deactivate`. 

### Installing Rig for Development

A development installation of rig can be created straight out of the repository
using [setuptools](https://pypi.python.org/pypi/setuptools) as usual:

    git clone git@github.com:project-rig/rig.git
    cd rig
    pip install .

In order to test the C-based simulated annealing placer kernel, you must also
install [`rig_c_sa`](https://github.com/project-rig/rig_c_sa) which requries a
C compiler and [libffi](https://sourceware.org/libffi/):

    pip install rig_c_sa

### Reporting Issues and Making Suggestions

Bug reports and suggestions can be made via the [GitHub issues
page](https://github.com/project-rig/rig/issues).

### Contributing

Contributions to the project are very welcome. To contribute, please make your
contribution off the master branch (making sure to update the [`CONTRIBUTORS.md
file`](CONTRIBUTORS.md)) and submit a GitHub pull request for review.

Testing
-------

Rig includes a test suite which should comprehensively test all of its
functionality: any bug discovered in Rig should simultaneously be considered a
bug in the test suite.

* The [py.test](http://pytest.org) framework is used to run Rig's tests.
* [Doctest](https://docs.python.org/2/library/doctest.html) is used to validate
  code samples in documentation.
* [pytest-cov](https://pypi.python.org/pypi/pytest-cov/1.8.1) to generate
  test-coverage reports. Since our tests intend to be comprehensive,
  test-coverage of less than 100% is not acceptable. Note that code coverage
  does not indicate comprehensive tests.
* [flake8](https://pypi.python.org/pypi/flake8) to enforce a [consistent code
  style](https://www.python.org/dev/peps/pep-0008/).
* [Tox](https://pypi.python.org/pypi/tox/1.8.1) can be used to run tests against
  all supported versions of Python.

The test suite requires a number of additional Python packages to run which can
be installed using::

    pip install -r requirements-test.txt

The test suite also requires that Rig itself be installed. Though a development
install is sufficient for running the tests, testing against a full installation
will also detect packaging faults (e.g. omitted binaries & support files).

### Running tests

Rigs tests are broken up into three groups which can be run as follows:

    $ py.test tests                                # The Rig test-suite
    $ py.test rig --doctest-modules                # Doctests in rig source code
    $ py.test docs --doctest-glob='*_doctest.rst'  # Doctests in Sphinx
                                                   # documentation whose
                                                   # filename ends with
                                                   # '_doctest.rst'.

Note: The first command only runs a subset of the full test suite which does not
require an attached SpiNNaker board.

Warning: Due to py.test modifying the Python module path, calling `py.test tests
rig docs` (i.e. with the test suite at the same time as the module source) will
fail for non-development installations. This is because the local 'rig' module
gets added to the Python path and so py.test complains about ambiguity when the
test-suite attempts to `import rig` and finds both a system version and a local
version.

#### Testing against local hardware

Some tests in the test suite require a connected SpiNNaker system.

**For a minimal live-hardware test,** the attached SpiNNaker system must not be
booted and have at least 2x2 SpiNNaker chips with the majority of cores
operational. To include tests which can operate against a generic SpiNNaker
system, run:

    py.test tests --spinnaker SPINN_HOSTNAME WIDTH HEIGHT

**For a comprehensive live-hardware test,** the test suite should be run
against a system consisting of a single SpiNN-5 board like so:

    py.test tests \
            --spinnaker SPINN_HOSTNAME 8 8 --spinn5 \
            --bmp BMP_HOSTNAME

### Test suite command line option reference

The test suite supports the following commandline arguments:

* `--spinnaker SPINN_HOSTNAME WIDTH HEIGHT` -- run tests against the specified
  SpiNNaker system.
* `--spinn5` -- include tests which specifically require a SpiNN-5 board to be
  attached.
* `--bmp BMP_HOSTNAME` -- run BMP communication tests against the suggested
  BMP. This option is only recommended for use against a single SpiNN-5 board
  since (by default) it power-cycles the board in 'slot 0'.
* `--no-boot` -- Skip the power-cycle BMP test and the SpiNNaker booting test.
  When this option is used, the attached SpiNNaker hardware must be already
  booted.

#### Testing against remote hardware

Booting a SpiNNaker board requires the (reliable) sending of packets to UDP
port 54321 which is frequently blocked by ISPs and is not reliable (since UDP
gives no guarantees, especially on the open internet). As a result, a proxy
server must be used to communicate with the board. A utility such as
[`spinnaker_proxy`](https://github.com/project-rig/spinnaker_proxy) can be used
alongside the test suite for this purpose.

See the [Travis setup](.travis.yml) for an example of this in use.

### Test coverage checking

If you're using a development install, to get a test coverage report run one of
the following:

    # Summary printed on the commandline
    py.test tests --cov rig --cov tests
    
    # Generate a full HTML report (in the htmlcov directory)
    py.test tests --cov rig --cov tests --cov-report html

Note: The test suite should be included in coverage reporting. This has, amongst
other things, helped find numerous tests which inadvertently never got run.

If you're using a system-wide install, you must tell coverage where to find the
Rig module's source. A simple utility is included in `utils/rig_path.py` which
prints the path of the installed Rig library. Tests can thus be run as follows:

    py.test tests --cov "$(./utils/rig_path.py)" --cov tests

### Code standards checking

To test for coding standards problems run:

    flake8 rig tests

### Using Tox

We also use [Tox](https://pypi.python.org/pypi/tox/1.8.1) to run tests against
multiple versions of Python. To do this just execute `tox` in the root
directory of the repository. Note that the included tox file requires all
supported Python versions to be installed.

To run against just a particular Python version use, for example:

    $ tox -e py27  # Runs against Python 2.7

Note that the first run of tox will be slow while the virtualenv is set up and
all dependencies downloaded and installed. Subsequent runs will reuse any
previously installed packages (when possible). When changing Rig's dependencies,
you should recreate the tox environment to ensure that all dependencies are
still fetched correctly:

    $ tox --recreate

### Continuous integration

We use [TravisCI](https://travis-ci.org/project-rig/rig) to automatically run
the whole Rig test test suite against a live SpiNN-5 board on any code pushed
to the Rig GitHub repository.

[Coveralls](https://coveralls.io/r/project-rig/rig) automatically checks that
the test-coverage of tests executed by TravisCI does not drop below 100%.

### Test suite novelties

* To assist some live board test functions, a simple SpiNNaker test program is
  loaded onto the machine. Its source can be found in
  [spinnaker_source/test_aplx](spinnaker_source/test_aplx). Note that a
  [precompiled binary](rig/binaries) is included with the repository to avoid
  the need to install a cross-compiler for most users.
* See the [conftest.py](tests/conftest.py) file for details of how the
  order in which tests are executed is constrained using `pytest.mark.order`
  and friends.


Documentation
-------------

Rig's documentation is built using [Sphinx](http://sphinx-doc.org/) with
docstrings in the code using [numpydoc](https://github.com/numpy/numpydoc) for
improved readability.

To install all additional Python packages required to build the Rig
documentation, run:

    pip install -r requirements-docs.txt

Note: `virtualenv` users using `--system-site-packages` and who have a
system-wide version of Sphinx installed may find that the build process fails.
To work around this, you can install a fresh copy of Sphinx in the `virtualenv`
using:

    pip install -I sphinx


### Building documentation locally

HTML documentation can be built using:

    cd docs
    make html

HTML documentation is created in [`docs/build/html/`](docs/build/html/).

### Online Documentation (ReadTheDocs)

Rig's documentation is automatically built and hosted by
[ReadTheDocs](https://readthedocs.org/projects/rig/). Two versions of the
documentation are provided:

* [Stable (default)](http://rig.readthedocs.org/en/stable/)
* [Master](http://rig.readthedocs.org/en/master/)

The 'stable' version is built from the most recently created tag (or in GitHub
parlance, 'release'). This should correspond with the version of Rig available
on PyPi.

The 'master' version is built automatically from the head of the master branch
in the repository. This is intended for use by Rig developers both as an
up-to-date reference and also to quickly verify that the documentation builds
the way they expect.

Documentation is currently built using Python 2 on ReadTheDocs due to issues
with their Python 3 support. 

### Numpy

The documentation can be built without Numpy being installed.  See
[`docs/source/conf.py`](docs/source/conf.py) for details of how this is made
possible.

Versioning and Releasing
------------------------

Rig is released on [PyPi](https://pypi.python.org/pypi/rig) and is therefore
available to install via pip. The [PEP440-compliant subset
of](http://legacy.python.org/dev/peps/pep-0440/#semantic-versioning) [Semantic
Versioning 2.0.0](http://semver.org/spec/v2.0.0.html) is used for version
numbering.

Release notes for each new version are included in the git tag for the release
and duplicated on the corresponding [GitHub release
page](https://github.com/project-rig/rig/releases).

### Making a release

To make a new release of Rig, the following actions must be performed.

1. The version number must be incremented in [`version.py`](rig/version.py) and
   committed to master.
2. A new tag, *annotated with the release notes*, must be added to this commit:
       
       ```
       $ git tag -a vX.Y.Z
       # ...enter release notes in tag annotation...
       $ git push origin vX.Y.Z
       ```
       
3. A [GitHub release](https://github.com/project-rig/rig/releases) should be
   created for the tag. The release title should be the same as the tag name
   and the release notes should be a verbatim copy of the release notes in the
   tag's annotation.
4. A source distribution should be packaged and uploaded to
   [PyPi](https://pypi.python.org/pypi/rig):
       
       ```
       $ python setup.py sdist
       # The next step requires twine (pip install twine)
       $ twine upload dist/rig-X.Y.Z.tar.gz
       ```
       
5. Documentation is released automatically on ReadTheDocs when the GitHub
   release is created.


Third-party services
--------------------

The following third-party services are used in the development and releasing of
Rig. If integration with any of these services fails, this should be considered
a bug.

* [Source code hosting (GitHub)](https://github.com/project-rig/rig)
* [Releases (PyPi)](https://pypi.python.org/pypi/rig)
* [Documentation hosting (ReadTheDocs)](https://readthedocs.org/projects/rig/)
* [Issue tracking (GitHub)](https://github.com/project-rig/rig/issues)
* [Continuous integration (TravisCI)](https://travis-ci.org/project-rig/rig)
* [Test-coverage checking (Coveralls)](https://coveralls.io/r/project-rig/rig)
* [SpiNNaker test hardware (University of Manchester)](http://apt.cs.manchester.ac.uk/)

If you feel that you require access to any of the above services, please raise
a GitHub Issue.
