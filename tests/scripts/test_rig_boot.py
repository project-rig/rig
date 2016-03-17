"""Test the boot command passes the correct arguments to boot when appropriate
arguments are given."""

import pytest

from rig.machine_control.machine_controller import SpiNNakerBootError

import rig.scripts.rig_boot as rig_boot

import mock

from rig.machine_control.boot import spin3_boot_options


@pytest.mark.parametrize("arguments", [
    # No args
    [],
    # Any dimension arguments (now deprecated)
    ["localhost", "3"],
    ["localhost", "8"],
    ["localhost", "8", "8"],
    # Too many predefined types
    ["localhost", "--spin1", "--spin2"],
])
def test_bad_args(arguments):
    with pytest.raises(SystemExit):
        rig_boot.main(arguments)


def test_already_booted(monkeypatch):
    # Should fail if system already booted
    monkeypatch.setattr(rig_boot.MachineController, "boot",
                        mock.Mock(return_value=False))
    assert rig_boot.main(["localhost"]) != 0


def test_boot_fails(monkeypatch):
    # Should fail if system responds to initial sver with non-SpiNNaker machine
    # type or booting fails.
    monkeypatch.setattr(rig_boot.MachineController, "boot",
                        mock.Mock(side_effect=SpiNNakerBootError))
    assert rig_boot.main(["localhost"]) != 0


@pytest.mark.parametrize("args,options", [
    # Defaults
    (["localhost"], {}),
    # Preset
    (["localhost", "--spin3"], spin3_boot_options),
])
def test_boot_options(monkeypatch, args, options):
    # Test that the correct boot command is called for the options given

    # Make it look as if the boot succeded
    monkeypatch.setattr(rig_boot.MachineController, "boot",
                        mock.Mock(return_value=True))

    # Check the boot occurred
    assert rig_boot.main(args) == 0
    rig_boot.MachineController.boot.assert_called_once_with(**options)
