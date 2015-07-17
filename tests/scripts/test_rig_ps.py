"""Test the ps command produces the correct output."""

import pytest

import mock

import rig.scripts.rig_ps as rig_ps

from rig.machine_control.scp_connection import \
    TimeoutError, FatalReturnCodeError

from rig.machine import Machine, Cores

from rig.machine_control.consts import AppState, RuntimeException


def test_match():
    assert rig_ps.match("foo", None)

    assert rig_ps.match("foo", ["foo"])
    assert rig_ps.match("foo", ["f.."])
    assert rig_ps.match("foo", ["foo", "bar"])
    assert rig_ps.match("foo", ["f..", "bar"])

    assert not rig_ps.match("baz", ["f..", "bar"])


def test_get_process_list():
    mc = mock.Mock()

    machine = Machine(2, 2, chip_resources={Cores: 2})
    mc.get_machine.return_value = machine

    def get_processor_status(x, y, p):
        status = mock.Mock()
        status.cpu_state = AppState.run if p == 0 else AppState.sync0
        status.rt_code = RuntimeException.none
        status.app_name = "SC&MP" if p == 0 else "test_app"
        status.app_id = 0 if p == 0 else 66
        return status
    mc.get_processor_status.side_effect = get_processor_status

    # Should list everything by default
    assert list(rig_ps.get_process_list(mc)) == [
        (0, 0, 0, AppState.run, RuntimeException.none, "SC&MP", 0),
        (0, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),

        (0, 1, 0, AppState.run, RuntimeException.none, "SC&MP", 0),
        (0, 1, 1, AppState.sync0, RuntimeException.none, "test_app", 66),

        (1, 0, 0, AppState.run, RuntimeException.none, "SC&MP", 0),
        (1, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),

        (1, 1, 0, AppState.run, RuntimeException.none, "SC&MP", 0),
        (1, 1, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
    ]

    # Should be able to filter by chip
    assert list(rig_ps.get_process_list(mc, 1, 0)) == [
        (1, 0, 0, AppState.run, RuntimeException.none, "SC&MP", 0),
        (1, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
    ]

    # Should be able to filter by core
    assert list(rig_ps.get_process_list(mc, 1, 0, 1)) == [
        (1, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
    ]

    # Should be able to filter by application
    assert list(rig_ps.get_process_list(mc, applications=["test.*"])) == [
        (0, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
        (0, 1, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
        (1, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
        (1, 1, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
    ]

    # Should be able to filter by state
    assert list(rig_ps.get_process_list(mc, states=["sync."])) == [
        (0, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
        (0, 1, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
        (1, 0, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
        (1, 1, 1, AppState.sync0, RuntimeException.none, "test_app", 66),
    ]


def test_get_process_list_dead_chip():
    mc = mock.Mock()

    machine = Machine(1, 1, chip_resources={Cores: 2})
    mc.get_machine.return_value = machine

    mc.get_processor_status.side_effect = FatalReturnCodeError(0x88)

    # Should list the failiure
    ps = list(rig_ps.get_process_list(mc))
    assert len(ps) == 2
    for x, y, p, app_state, rte, name, app_id in ps:
        assert x == 0
        assert y == 0
        assert 0 <= p < 2
        assert app_state.name == \
            "FatalReturnCodeError: RC_CPU: Bad CPU number."
        assert bool(rte) is False
        assert name == ""
        assert app_id == -1


def test_bad_args():
    # No hostname
    with pytest.raises(SystemExit):
        rig_ps.main([])

    # X but no Y
    with pytest.raises(SystemExit):
        rig_ps.main(["localhost", "0"])

    # Invalid X, Y and core
    with pytest.raises(SystemExit):
        rig_ps.main(["localhost", "foo", "bar"])
    with pytest.raises(SystemExit):
        rig_ps.main(["localhost", "0", "0", "baz"])


def test_no_machine(monkeypatch):
    # Should fail if nothing responds
    mc = mock.Mock()
    mc.get_software_version = mock.Mock(side_effect=TimeoutError())

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_ps, "MachineController", MC)

    assert rig_ps.main(["localhost"]) != 0


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
    monkeypatch.setattr(rig_ps, "MachineController", MC)

    assert rig_ps.main(["localhost"]) != 0


def test_output(monkeypatch, capsys):
    # Test that the output is formatted as expected
    mc = mock.Mock()
    info = mock.Mock()
    info.version_string = "SpiNNaker/SC&MP"
    info.version = 1.337
    mc.get_software_version.return_value = info

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_ps, "MachineController", MC)

    get_process_list = mock.Mock(return_value=[
        (0, 1, 2, AppState.run, RuntimeException.none, "SC&MP", 0),
        (3, 4, 5, AppState.runtime_exception, RuntimeException.reset,
         "test_app", 66),
    ])

    monkeypatch.setattr(rig_ps, "get_process_list", get_process_list)

    # XXX: Does not test arguments are parsed correctly...
    assert rig_ps.main(["localhost"]) == 0

    stdout, stderr = capsys.readouterr()

    assert stdout == (
        "X   Y   P   State             Application      App ID\n"
        "--- --- --- ----------------- ---------------- ------\n"
        "  0   1   2 run               SC&MP                 0 \n"
        "  3   4   5 runtime_exception test_app             66 reset\n"
    )
