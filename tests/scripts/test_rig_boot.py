"""Test the boot command passes the correct arguments to boot when appropriate
arguments are given."""

import pytest

from rig.machine_control.machine_controller import SpiNNakerBootError

import rig.scripts.rig_boot as rig_boot

import mock

import tempfile

import os

from rig.machine_control.boot import spin3_boot_options, spin5_boot_options

spin3_boot_options_modified = spin3_boot_options.copy()
spin3_boot_options_modified["width"] = 8
spin3_boot_options_modified["height"] = 4

spin5_boot_options_modified = spin5_boot_options.copy()
spin5_boot_options_modified["width"] = 48
spin5_boot_options_modified["height"] = 24


@pytest.mark.parametrize("arguments", [
    # No args
    [],
    # No width/height/predfined type
    ["localhost"],
    # Non-multiple-of-three number of boards
    ["localhost", "8"],
    # Wrong type
    ["localhost", "a", "8"],
    ["localhost", "8", "a"],
    ["localhost", "a", "a"],
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
    assert rig_boot.main(["localhost", "8", "8"]) != 0


def test_boot_fails(monkeypatch):
    # Should fail if system responds to initial sver with non-SpiNNaker machine
    # type or booting fails.
    monkeypatch.setattr(rig_boot.MachineController, "boot",
                        mock.Mock(side_effect=SpiNNakerBootError))
    assert rig_boot.main(["localhost", "8", "8"]) != 0


@pytest.fixture(scope="module")
def binary(request):
    content = b"Hello, rig!"
    temp = tempfile.NamedTemporaryFile(delete=False)
    temp.write(content)
    temp.close()

    def teardown():
        temp.close()
        os.unlink(temp.name)
    request.addfinalizer(teardown)

    return (temp.name, content)


@pytest.mark.parametrize("args,options", [
    # Width/height only
    (["localhost", "8", "4"], {"width": 8,
                               "height": 4,
                               "hardware_version": 0,
                               "led_config": 0x00000001}),
    # Number of boards only only
    (["localhost", "3"], {"width": 12,
                          "height": 12,
                          "hardware_version": 0,
                          "led_config": 0x00000001}),
    (["localhost", "24"], {"width": 48,
                           "height": 24,
                           "hardware_version": 0,
                           "led_config": 0x00000001}),
    # Hardware version set
    (["localhost", "8", "4", "--hardware-version", "2"],
     {"width": 8,
      "height": 4,
      "hardware_version": 2,
      "led_config": 0x00000001}),
    # LED config set
    (["localhost", "8", "4", "--led-config", "3"],
     {"width": 8,
      "height": 4,
      "hardware_version": 0,
      "led_config": 0x00000003}),
    # Preset only
    (["localhost", "--spin3"], spin3_boot_options),
    # Preset with explicit options overriding
    (["localhost", "8", "4", "--spin3"], spin3_boot_options_modified),
    (["localhost", "24", "--spin5"], spin5_boot_options_modified),
])
@pytest.mark.parametrize("specify_binary", [True, False])
def test_boot_options(monkeypatch, args, options, binary, specify_binary):
    # Test that the correct boot command is called for the options given

    # Make it look as if the boot succeded
    monkeypatch.setattr(rig_boot.MachineController, "boot",
                        mock.Mock(return_value=True))

    args = args[:]
    if specify_binary:
        args.extend(["--binary", binary[0]])

    # Check the boot occurred
    assert rig_boot.main(args) == 0
    if specify_binary:
        rig_boot.MachineController.boot.assert_called_once_with(
            boot_data=binary[1], **options)
    else:
        rig_boot.MachineController.boot.assert_called_once_with(
            boot_data=None, **options)
