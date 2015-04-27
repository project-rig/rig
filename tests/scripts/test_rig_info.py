"""Test the info command produces sane output when presented with various
machine types."""

import pytest

import mock

import rig.scripts.rig_info as rig_info

from rig.machine_control.scp_connection import TimeoutError

from rig.machine import Cores, SDRAM, SRAM, Links, Machine

from rig.machine_control.bmp_controller import ADCInfo


def test_bad_args():
    with pytest.raises(SystemExit):
        rig_info.main([])


def test_no_machine(monkeypatch):
    # Should fail if nothing responds
    mc = mock.Mock()
    mc.get_software_version = mock.Mock(side_effect=TimeoutError)

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_info, "MachineController", MC)

    assert rig_info.main(["localhost"]) != 0


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
    monkeypatch.setattr(rig_info, "MachineController", MC)

    assert rig_info.main(["localhost"]) != 0


@pytest.mark.parametrize("torus", [True, False])
def test_spinnaker(monkeypatch, capsys, torus):
    # Test with (fake) SpiNNaker hardware attached. Output is checked by just
    # ensuring certain strings are present. This is not foolproof but just a
    # basic sanity check.
    mc = mock.Mock()
    info = mock.Mock()
    info.version_string = "Mock/SpiNNaker"
    info.version = 1.337
    info.build_date = 0
    mc.get_software_version.return_value = info

    width = 4
    height = 8
    chip_resources = {Cores: 18, SDRAM: 1, SRAM: 1}
    chip_resource_exceptions = {(0, 0): {Cores: 17, SDRAM: 1, SRAM: 1}}
    dead_chips = set([(1, 1)])
    dead_links = set([(0, 0, Links.north)])
    if not torus:
        # Kill the wrap-around links
        for x in range(width):
            dead_links.add((x, 0, Links.south))
            dead_links.add((x, 0, Links.south_west))
            dead_links.add((x, height - 1, Links.north))
            dead_links.add((x, height - 1, Links.north_east))
        for y in range(height):
            dead_links.add((0, y, Links.west))
            dead_links.add((0, y, Links.south_west))
            dead_links.add((width - 1, y, Links.east))
            dead_links.add((width - 1, y, Links.north_east))
    machine = Machine(width, height,
                      chip_resources, chip_resource_exceptions,
                      dead_chips, dead_links)
    mc.get_machine.return_value = machine

    app_state = mock.Mock()
    app_state.app_name = "mockapp"
    app_state.cpu_state.name = "mockstate"
    mc.get_processor_status.return_value = app_state

    MC = mock.Mock()
    MC.return_value = mc
    monkeypatch.setattr(rig_info, "MachineController", MC)

    assert rig_info.main(["localhost"]) == 0

    stdout, stderr = capsys.readouterr()

    assert "SpiNNaker" in stdout  # Hardware type
    assert "Mock" in stdout  # Software name
    assert "v1.337" in stdout  # Software version
    assert "1970" in stdout  # Software builid date
    assert "4x8" in stdout  # System dimensions
    assert "Working chips: 31" in stdout  # Live chip count
    assert "18 cores: 30" in stdout  # Core numbers histogram
    assert "17 cores: 1" in stdout  # Core numbers histogram
    if torus:  # Network topology
        assert "torus" in stdout
    else:
        assert "mesh" in stdout
    assert "mockapp" in stdout  # Mock app status
    assert "557 mockstate" in stdout  # State count


@pytest.mark.parametrize("tmp_ext_0", [234.0, None])
@pytest.mark.parametrize("tmp_ext_1", [234.1, None])
@pytest.mark.parametrize("fan_0", [1234, None])
@pytest.mark.parametrize("fan_1", [2345, None])
def test_bmp(monkeypatch, capsys, tmp_ext_0, tmp_ext_1, fan_0, fan_1):
    # Test with (fake) BMP hardware attached. Output is checked by just
    # ensuring certain strings are present. This is not foolproof but just a
    # basic sanity check.
    info = mock.Mock()
    info.version_string = "Mock/BMP"
    info.version = 1.337
    info.build_date = 0
    info.code_block = 7331
    info.board_id = 1234

    adc = ADCInfo(112.00, 112.10, 112.20,  # 1.2v
                  118.00,  # 1.8v
                  133.00,  # 3.3v
                  120.00,  # 12v
                  123.0, 123.1,  # Temp top/btm
                  tmp_ext_0, tmp_ext_1,  # Temp ext
                  fan_0, fan_1)  # Fans

    mc = mock.Mock()
    mc.get_software_version.return_value = info
    bc = mock.Mock()
    bc.get_software_version.return_value = info
    bc.read_adc.return_value = adc

    MC = mock.Mock()
    MC.return_value = mc
    BC = mock.Mock()
    BC.return_value = bc
    monkeypatch.setattr(rig_info, "MachineController", MC)
    monkeypatch.setattr(rig_info, "BMPController", BC)

    assert rig_info.main(["localhost"]) == 0

    stdout, stderr = capsys.readouterr()

    assert "BMP" in stdout  # Hardware type
    assert "Mock" in stdout  # Software name
    assert "v1.337" in stdout  # Software version
    assert "1970" in stdout  # Software builid date
    assert "7331" in stdout  # Code block used
    assert "1234" in stdout  # Slot number
    assert "112.00 V" in stdout  # Voltages
    assert "112.10 V" in stdout
    assert "112.20 V" in stdout
    assert "118.00 V" in stdout
    assert "133.00 V" in stdout
    assert "120.00 V" in stdout
    assert "123.0 *C" in stdout  # Internal temperature probes
    assert "123.1 *C" in stdout

    if tmp_ext_0 is not None:  # External temperate probes
        assert "Temperature external 0" in stdout
        assert "{:.1f}".format(tmp_ext_0) in stdout
    else:
        assert "Temperature external 0" not in stdout

    if tmp_ext_1 is not None:
        assert "Temperature external 1" in stdout
        assert "{:.1f}".format(tmp_ext_1) in stdout
    else:
        assert "Temperature external 1" not in stdout

    if fan_0 is not None:  # Fans
        assert "Fan 0 speed" in stdout
        assert "{} RPM".format(fan_0) in stdout
    else:
        assert "Fan 0 speed" not in stdout

    if fan_1 is not None:
        assert "Fan 1 speed" in stdout
        assert "{} RPM".format(fan_1) in stdout
    else:
        assert "Fan 1 speed" not in stdout
