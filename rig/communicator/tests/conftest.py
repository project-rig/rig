import pytest


@pytest.fixture(scope='session')
def spinnaker_ip(request):
    return request.config.getoption('spinnaker', skip=True)


def pytest_addoption(parser):
    # Add the option to run tests against a SpiNNaker machine
    parser.addoption("--spinnaker", help="Run tests on a SpiNNaker machine. "
                                         "Specify the IP address or hostname "
                                         "of the SpiNNaker machine to use.")
