import pytest


@pytest.fixture(scope='session')
def spinnaker_ip(request):
    return request.config.getoption('spinnaker', skip=True)[0]


@pytest.fixture(scope='session')
def spinnaker_width(request):
    return int(request.config.getoption('spinnaker', skip=True)[1])


@pytest.fixture(scope='session')
def spinnaker_height(request):
    return int(request.config.getoption('spinnaker', skip=True)[2])


def pytest_addoption(parser):
    # Add the option to run tests against a SpiNNaker machine
    parser.addoption("--no-boot", action="store_false",
                     help="Skip booting the board during tests.")
    parser.addoption("--spinnaker", nargs=3,
                     help="Run tests on a SpiNNaker machine. "
                          "Specify the IP address or hostname "
                          "of the SpiNNaker machine to use and the width and "
                          "the height of the machine.")


# From pytest.org
def pytest_runtest_makereport(item, call):
    if "incremental" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item


def pytest_runtest_setup(item):
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" % previousfailed.name)

    for (mark, option, message) in [
            ("no_boot", "--no-boot", "don't (re)boot the SpiNNaker machine")]:
        if getattr(item.obj, mark, None) and not item.config.getoption(option):
            pytest.skip(message)
