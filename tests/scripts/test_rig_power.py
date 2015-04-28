"""Test the power command passes the correct arguments to BMPController when
appropriate arguments are given."""

import pytest

from rig.machine_control.scp_connection import TimeoutError

import rig.scripts.rig_power as rig_power

import mock


@pytest.mark.parametrize("arguments", [
    # No args
    [],
    # Unrecognised power options
    ["localhost", ""],
    ["localhost", "8"],
    # Bad ranges
    ["localhost", "--board", ""],
    ["localhost", "--board=,"],
    ["localhost", "--board=0,"],
    ["localhost", "--board=0,,1"],
    ["localhost", "--board=0-"],
    ["localhost", "--board=-0"],
    ["localhost", "--board=0--2"],
    ["localhost", "--board=0:0"],
    ["localhost", "--board=5-3"],
    ["localhost", "--board=a"],
    # Bad delays
    ["localhost", "--power-on-delay=a"],
    ["localhost", "--power-on-delay=-1"],
])
def test_bad_args(arguments):
    with pytest.raises(SystemExit):
        rig_power.main(arguments)


def test_not_bmp(monkeypatch):
    # Should fail if system responds to initial sver with non-BMP machine
    # type.
    bc = mock.Mock()
    info = mock.Mock()
    info.version_string = "Mock/SpiNNaker"
    info.version = 1.337
    bc.get_software_version.return_value = info

    BC = mock.Mock()
    BC.return_value = bc
    monkeypatch.setattr(rig_power, "BMPController", BC)

    assert rig_power.main(["localhost"]) != 0


def test_timeout_fails(monkeypatch):
    # Should fail if system doesn't to initial sver
    bc = mock.Mock()
    bc.get_software_version = mock.Mock(side_effect=TimeoutError)

    BC = mock.Mock()
    BC.return_value = bc
    monkeypatch.setattr(rig_power, "BMPController", BC)

    assert rig_power.main(["localhost"]) != 0


@pytest.mark.parametrize("args,options", [
    # Defaults to powering on
    (["localhost"], {"state": True, "board": {0}}),
    # Power on
    (["localhost", "1"], {"state": True, "board": {0}}),
    (["localhost", "on"], {"state": True, "board": {0}}),
    # Power off
    (["localhost", "0"], {"state": False, "board": {0}}),
    (["localhost", "off"], {"state": False, "board": {0}}),
    # Specify ranges of boards
    (["localhost", "-b=3"], {"state": True, "board": {3}}),
    (["localhost", "--board=0"], {"state": True, "board": {0}}),
    (["localhost", "--board=1"], {"state": True, "board": {1}}),
    (["localhost", "--board=0,2,3"], {"state": True, "board": {0, 2, 3}}),
    (["localhost", "--board=0-0"], {"state": True, "board": {0}}),
    (["localhost", "--board=0-2"], {"state": True, "board": {0, 1, 2}}),
    (["localhost", "--board=1,5-6"], {"state": True, "board": {1, 5, 6}}),
    # Power-on delay
    (["localhost", "--power-on-delay=1.0"], {"state": True, "board": {0},
                                             "post_power_on_delay": 1.0}),
    (["localhost", "-d=0.0"], {"state": True, "board": {0},
                               "post_power_on_delay": 0.0}),
])
def test_power_options(monkeypatch, args, options):
    # Test that the correct power command is called for the options given

    bc = mock.Mock()
    info = mock.Mock()
    info.version_string = "Mock/BMP"
    info.version = 1.337
    bc.get_software_version.return_value = info

    BC = mock.Mock()
    BC.return_value = bc
    monkeypatch.setattr(rig_power, "BMPController", BC)

    # Check the boot occurred
    assert rig_power.main(args) == 0
    BC.assert_called_once_with(args[0])
    bc.set_power.assert_called_once_with(**options)
