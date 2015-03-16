"""Test the boot command passes the correct arguments to boot when appropriate
arguments are given."""

import pytest

from rig.machine_control.scp_connection import TimeoutError

import rig.scripts.rig_boot as rig_boot

import mock

import tempfile

import os

from rig.machine_control.boot import spin3_boot_options

spin3_boot_options_modified = spin3_boot_options.copy()
spin3_boot_options_modified["width"] = 8
spin3_boot_options_modified["height"] = 4


@pytest.mark.parametrize("arguments", [
    # No args
    [],
    # No width/height/predfined type
    ["localhost"],
    # No height
    ["localhost", "8"],
    ["localhost", "8", "--spin3"],
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
    MC = mock.Mock()
    mc = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_boot, "MachineController", MC)

    info = mock.Mock()
    mc.get_software_version.return_value = info
    info.version_string = "Mock/SpiNNaker"
    info.version = 1.337

    assert rig_boot.main(["localhost", "8", "8"]) != 0


def test_not_spinnaker(monkeypatch):
    # Should fail if system responds to initial sver with non-SpiNNaker machine
    # type.
    mc = mock.Mock()
    info = mock.Mock()
    info.version_string = "Mock/Tester"
    info.version = 1.337
    mc.get_software_version.return_value = info

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_boot, "MachineController", MC)

    assert rig_boot.main(["localhost", "8", "8"]) != 0


def test_boot_fails(monkeypatch):
    # Should fail if system responds to initial sver with non-SpiNNaker machine
    # type.
    mc = mock.Mock()
    mc.get_software_version = mock.Mock(side_effect=TimeoutError)

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_boot, "MachineController", MC)

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
])
@pytest.mark.parametrize("specify_binary", [True, False])
def test_boot_options(monkeypatch, args, options, binary, specify_binary):
    # Test that the correct boot command is called for the options given

    # Make it look as if the boot succeded
    mc = mock.Mock()
    first_call = [True]

    def get_software_version(x, y):
        assert x == 0
        assert y == 0
        if first_call[0]:
            first_call[0] = False
            raise TimeoutError()
        else:
            info = mock.Mock()
            info.version_string = "MockBoot/SpiNNaker"
            info.version = 1.337
            return info
    mc.get_software_version = mock.Mock(side_effect=get_software_version)

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_boot, "MachineController", MC)

    args = args[:]
    if specify_binary:
        args.extend(["--binary", binary[0]])

    # Check the boot occurred
    assert rig_boot.main(args) == 0
    if specify_binary:
        mc.boot.assert_called_once_with(boot_data=binary[1], **options)
    else:
        mc.boot.assert_called_once_with(boot_data=None, **options)
