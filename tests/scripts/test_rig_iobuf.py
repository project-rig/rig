"""Test the iobuf command produces the correct output."""

import pytest

import mock

import rig.scripts.rig_iobuf as rig_iobuf

from rig.machine_control.scp_connection import TimeoutError


def test_bad_args():
    with pytest.raises(SystemExit):
        rig_iobuf.main([])
    with pytest.raises(SystemExit):
        rig_iobuf.main(["localhost", "foo", "bar", "baz"])


def test_no_machine(monkeypatch):
    # Should fail if nothing responds
    mc = mock.Mock()
    mc.get_software_version = mock.Mock(side_effect=TimeoutError)

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_iobuf, "MachineController", MC)

    assert rig_iobuf.main(["localhost", "0", "0", "1"]) != 0


def test_unknown_arch(monkeypatch):
    # Should fail if system responds to initial sver with non-SpiNNaker/BMP
    # machine type.
    mc = mock.Mock()
    info = mock.Mock()
    info.version_string = "Mock/Tester"
    info.version = 1.337
    mc.get_software_version.return_value = info

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_iobuf, "MachineController", MC)

    assert rig_iobuf.main(["localhost", "0", "0", "1"]) != 0


def test_iobuf(monkeypatch, capsys):
    # Test with (fake) contents of the IOBUF.
    mc = mock.Mock()
    mc.get_iobuf.return_value = "This is the correct output."
    info = mock.Mock()
    info.version_string = "SpiNNaker/SC&MP"
    info.version = 1.337
    mc.get_software_version.return_value = info

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_iobuf, "MachineController", MC)

    assert rig_iobuf.main(["localhost", "0", "0", "1"]) == 0

    stdout, stderr = capsys.readouterr()

    assert stdout == "This is the correct output."
