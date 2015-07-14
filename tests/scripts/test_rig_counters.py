"""Test the counters command produces the correct output."""

import pytest

import os

import mock

import subprocess

from tempfile import mkstemp

from six import StringIO

import rig.scripts.rig_counters as rig_counters

from rig.machine_control.scp_connection import TimeoutError

from rig.machine import Machine

from rig.machine_control.machine_controller import RouterDiagnostics


def test_sample_counters():
    mc = mock.Mock()
    mc.get_router_diagnostics.return_value = RouterDiagnostics(
        *(0 for _ in RouterDiagnostics._fields))
    machine = Machine(2, 2)

    # All counters should have been sampled
    counters = rig_counters.sample_counters(mc, machine)
    assert set(counters) == set(machine)
    assert all(all(v == 0 for v in counters[xy]) for xy in counters)


def test_deltas():
    # In this example we include both unchanging, positive and wrap-around
    # changes
    last = {
        (0, 0): RouterDiagnostics(1, 0xFFFFFFFF, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0),
        (1, 0): RouterDiagnostics(0xFFFFFFFF, 1, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0),
    }
    this = {
        (0, 0): RouterDiagnostics(10, 1, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0),
        (1, 0): RouterDiagnostics(2, 11, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0),
    }
    assert rig_counters.deltas(last, this) == {
        (0, 0): RouterDiagnostics(9, 2, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0),
        (1, 0): RouterDiagnostics(3, 10, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0,
                                  0, 0, 0, 0),
    }


@pytest.mark.parametrize("keyboard_interrupt", [False, True])
@pytest.mark.parametrize("multiple", [False, True])
@pytest.mark.parametrize("silent", [False, True])
def test_press_enter(capsys, monkeypatch, keyboard_interrupt, multiple,
                     silent):
    # Inputs should be safely terminated by EOF or ^C
    mock_input = mock.Mock(side_effect=["", "",
                                        KeyboardInterrupt
                                        if keyboard_interrupt else
                                        EOFError])
    monkeypatch.setattr(rig_counters, "input", mock_input)

    responses = list(rig_counters.press_enter(multiple, silent)())

    # Should have the right number of responses
    if multiple:
        assert responses == ["", ""]
    else:
        assert responses == [""]

    # Sould only print instructions if not silent. Should add a newline when a
    # ^C or EOF terminates the output
    out, err = capsys.readouterr()
    if silent:
        assert out == ""
        assert err == ""
    else:
        assert out == ""
        if multiple:
            assert err == "<press enter> <press enter> <press enter> \n"
        else:
            assert err == "<press enter> "


@pytest.mark.parametrize("keyboard_interrupt", [False, True])
def test_run_command(capsys, monkeypatch, keyboard_interrupt):
    # Commands should be safely terminated by ^C
    mock_call = mock.Mock(side_effect=[KeyboardInterrupt
                                       if keyboard_interrupt else 0])
    monkeypatch.setattr(subprocess, "call", mock_call)

    f = rig_counters.run_command(["foo", "--bar"])

    # Shouldn't be called until we start the generator
    assert not mock_call.called

    # Should not propagate a KeyboardInterrupt
    assert list(f()) == [""]

    # Should now have been called
    mock_call.assert_called_once_with(["foo", "--bar"])

    # Should be silent on stderr/stdout
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


@pytest.mark.parametrize("multiple", [False, True])
@pytest.mark.parametrize("detailed", [False, True])
def test_monitor_counters(multiple, detailed):
    mock_mc = mock.Mock()
    mock_mc.get_machine.return_value = Machine(2, 2)

    cur_count = {xy: 0 for xy in mock_mc.get_machine()}

    def get_router_diagnostics(x, y):
        counters = RouterDiagnostics(*(cur_count[(x, y)] * (i + 1)
                                       for i in range(16)))
        cur_count[(x, y)] += 1
        return counters
    mock_mc.get_router_diagnostics.side_effect = get_router_diagnostics

    output = StringIO()
    counters = ["dropped_multicast", "local_multicast"]

    f = mock.Mock(return_value=["", ""] if multiple else [""])
    rig_counters.monitor_counters(mock_mc, output, counters, detailed, f)

    # Should have a fully printed table
    output = output.getvalue()
    lines = output.rstrip("\n").split("\n")

    if detailed:
        assert len(lines) >= 1 + 4

        # Order of fields should be as specified
        assert lines[0] == "time,x,y,dropped_multicast,local_multicast"
        assert lines[1] == "0.0,0,0,9,1"
        assert lines[2] == "0.0,0,1,9,1"
        assert lines[3] == "0.0,1,0,9,1"
        assert lines[4] == "0.0,1,1,9,1"

        if multiple:
            assert len(lines) == 1 + 4 + 4
            assert lines[5] == "0.0,0,0,9,1"
            assert lines[6] == "0.0,0,1,9,1"
            assert lines[7] == "0.0,1,0,9,1"
            assert lines[8] == "0.0,1,1,9,1"
        else:
            assert len(lines) == 1 + 4
    else:
        assert len(lines) >= 2

        # Order of fields should be as specified
        assert lines[0] == "time,dropped_multicast,local_multicast"
        assert lines[1] == "0.0,36,4"

        if multiple:
            assert len(lines) == 3
            assert lines[2] == "0.0,36,4"
        else:
            assert len(lines) == 2


def test_bad_args():
    # No hostname
    with pytest.raises(SystemExit):
        rig_counters.main([])

    # Command and multiple specified at same time
    with pytest.raises(SystemExit):
        rig_counters.main(["localhost", "-m", "-c", "true"])


def test_no_machine(monkeypatch):
    # Should fail if nothing responds
    mc = mock.Mock()
    mc.get_software_version = mock.Mock(side_effect=TimeoutError)

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_counters, "MachineController", MC)

    assert rig_counters.main(["localhost"]) != 0


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
    monkeypatch.setattr(rig_counters, "MachineController", MC)

    assert rig_counters.main(["localhost"]) != 0


@pytest.mark.parametrize("counter_args,counters", [
    # Default to just dropped multicast
    ([], ["dropped_multicast"]),
    # Single counter
    (["--drop-nn"], ["dropped_nearest_neighbour"]),
    # Multiple counters
    (["--drop-nn", "--local-p2p"], ["dropped_nearest_neighbour", "local_p2p"]),
])
@pytest.mark.parametrize("output_to_file", [None, "-", "temp"])
@pytest.mark.parametrize("use_command", [True, False])
def test_command(monkeypatch, capsys, counter_args, counters, output_to_file,
                 use_command):
    # Make sure the less-trivial commandline arguments are handled correctly
    mock_mc = mock.Mock()
    mock_mc.get_machine.return_value = Machine(2, 2)
    mock_mc.get_router_diagnostics.return_value = RouterDiagnostics(*[0] * 16)
    mock_info = mock.Mock()
    mock_info.version_string = "SpiNNaker"
    mock_mc.get_software_version.return_value = mock_info

    if use_command:
        mock_call = mock.Mock(return_value=0)
        monkeypatch.setattr(subprocess, "call", mock_call)
        command_args = ["-c"]
    else:
        mock_input = mock.Mock(side_effect=["", EOFError])
        monkeypatch.setattr(rig_counters, "input", mock_input)
        command_args = []

    monkeypatch.setattr(rig_counters, "MachineController",
                        mock.Mock(return_value=mock_mc))

    if output_to_file is None:
        output_args = []
        uses_stdout = True
    elif output_to_file is "-":
        output_args = ["--output", "-"]
        uses_stdout = True
    else:
        # Make a tempoary file to output into
        _, tempfile = mkstemp()
        output_args = ["--output", tempfile]
        uses_stdout = False

    assert rig_counters.main(["localhost"] +
                             output_args +
                             counter_args +
                             command_args) == 0

    # Make sure the right trigger was used
    if use_command:
        assert mock_call.called
    else:
        assert mock_input.called

    # Get the output from the selected file
    if uses_stdout:
        output, _ = capsys.readouterr()
    else:
        output, _ = capsys.readouterr()
        assert output == ""
        with open(tempfile, "r") as f:
            output = f.read()

    # Make sure the output is correct
    lines = output.rstrip("\n").split("\n")
    assert len(lines) == 2
    assert lines[0] == "time,{}".format(",".join(counters))
    assert lines[1] == "0.0,{}".format(",".join("0" for _ in counters))

    # Delete the temporary file
    if not uses_stdout:
        os.remove(tempfile)
