import mock
import pkg_resources
import pytest
import six
from six import iteritems, itervalues
import struct
import tempfile
import os
import time
import itertools
import warnings

from test_scp_connection import SendReceive, mock_conn  # noqa

from rig.machine_control.consts import (
    SCPCommands, LEDAction, NNCommands, NNConstants)
from rig.machine_control.machine_controller import (
    MachineController, SpiNNakerBootError, SpiNNakerMemoryError, MemoryIO,
    SpiNNakerRouterError, SpiNNakerLoadingError, SystemInfo, CoreInfo,
    ChipInfo, ProcessorStatus, unpack_routing_table_entry,
)
from rig.machine_control.packets import SCPPacket
from rig.machine_control.scp_connection import \
    SCPConnection, SCPError
from rig.machine_control import boot, regions, consts, struct_file

from rig.machine import Links, Machine

from rig.routing_table import RoutingTableEntry, Routes


@pytest.fixture(scope="module")
def controller(spinnaker_ip):
    return MachineController(spinnaker_ip)


@pytest.fixture(scope="module")
def live_system_info(controller):
    return controller.get_system_info()


@pytest.fixture
def cn():
    cn = MachineController("localhost")
    cn._scp_data_length = 256
    return cn


@pytest.fixture
def mock_controller():
    cn = mock.Mock(spec=MachineController)
    return cn


@pytest.fixture
def aplx_file(request):
    """Create an APLX file containing nonsense data."""
    # Create the APLX data
    aplx_file = tempfile.NamedTemporaryFile(delete=False)
    test_string = b"Must be word aligned"
    assert len(test_string) % 4 == 0
    aplx_file.write(test_string * 100)
    aplx_file.close()

    def teardown():
        aplx_file.close()
        os.unlink(aplx_file.name)
    request.addfinalizer(teardown)

    return aplx_file.name


@pytest.mark.order_id("spinnaker_boot", "spinnaker_hw_test")
@pytest.mark.order_after("bmp_power_cycle")
@pytest.mark.no_boot  # Don't run if booting is disabled
def test_boot(controller, spinnaker_width, spinnaker_height):
    """Test that the board can be booted."""
    # Boot the board (which will throw an exception if the board could not be
    # booted)
    controller.boot(width=spinnaker_width, height=spinnaker_height)

    # To ensure that the check worked, also explicitly check that the board is
    # booted, messy!
    sver = controller.get_software_version(0, 0, 0)
    assert "SpiNNaker" in sver.version_string
    assert sver.version >= 1.3

    # Make sure if we try and boot again, it is not re-booted
    assert not controller.boot(width=spinnaker_width, height=spinnaker_height)


@pytest.mark.order_id("spinnaker_hw_test")
@pytest.mark.order_after("spinnaker_boot")
@pytest.mark.incremental
class TestMachineControllerLive(object):
    """Test the machine controller against a running SpiNNaker machine."""
    def test_get_software_version(self, controller, spinnaker_width,
                                  spinnaker_height):
        """Test getting the software version data."""
        # (Assuming a 4-node board) Get the software version for a number of
        # cores.
        for x in range(2):
            for y in range(2):
                sver = controller.get_software_version(x=x, y=y, processor=0)
                assert sver.virt_cpu == 0
                assert "SpiNNaker" in sver.version_string
                assert sver.version >= 1.3
                assert sver.position == (x, y)

    def test_get_ip_address(self, controller):
        """Test getting the IP address."""
        # Chip 0, 0 should report an IP address (since it is what we're
        # connected via, though note that we can't check the IP since we may be
        # connected via a proxy).
        assert isinstance(controller.get_ip_address(0, 0), str)

        # Chip 1, 1 should not report an IP address (since in no existing
        # hardware does it have an Ethernet connection)..
        assert controller.get_ip_address(1, 1) is None

    def test_write_and_read(self, controller):
        """Test write and read capabilities by writing a string to SDRAM and
        then reading back in a different order.
        """
        data = b'Hello, SpiNNaker'

        # You put the data in
        with controller(x=0, y=0, p=0):
            controller.write(0x60000000, data[0:4])
            controller.write(0x60000004, data[4:6])
            controller.write(0x60000006, data[6:])

        # You take the data out
        with controller(x=0, y=0, p=1):
            assert controller.read(0x60000000, 1) == data[0:1]
            assert controller.read(0x60000000, 2) == data[0:2]
            assert controller.read(0x60000000, 4) == data[0:4]

        # Read out the entire string
        with controller(x=0, y=0, p=1):
            assert controller.read(0x60000000, len(data)) == data

    def test_write_and_read_across_link(self, controller):
        """Test link-write and read capabilities by writing a string to SDRAM
        on another chip and then reading back.
        """
        data = b'PEEK and POKE!!!'  # Length is a multiple of words

        # You put the data in
        with controller(x=0, y=0, link=Links.north):
            controller.write_across_link(0x60000000, data[0:4])
            controller.write_across_link(0x60000004, data[4:])

        # You take the data out
        with controller(x=0, y=0, link=Links.north):
            assert controller.read_across_link(0x60000000, 4) == data[0:4]
            assert controller.read_across_link(0x60000000, len(data)) == data

        # And check the data really was put on another chip
        with controller(x=0, y=1):
            assert controller.read(0x60000000, len(data)) == data

    def test_write_and_read_struct_values(self, controller):
        """Test reading a struct value, writing a new value and then resetting
        the value.
        """
        with controller(x=0, y=1):
            controller.read_struct_field("sv", "p2p_addr") == 0x0 | 0x0100

            # Read back the led->period, set it to something else and then
            # restore it.
            led_period = controller.read_struct_field("sv", "led_period")
            controller.write_struct_field("sv", "led_period", 100)
            assert controller.read_struct_field("sv", "led_period") == 100
            controller.write_struct_field("sv", "led_period", led_period)

    def test_set_get_clear_iptag(self, controller):
        # Get our address, then add a new IPTag pointing
        # **YUCK**
        ip_addr = controller.connections[None].sock.getsockname()[0]
        port = 1234
        iptag = 7

        with controller(x=0, y=0):
            # Set IPTag 7 with the parameters from above
            controller.iptag_set(iptag, ip_addr, port)

            # Get the IPtag and check that it is as we set it
            ip_tag = controller.iptag_get(iptag)
            assert ip_addr == ip_tag.addr
            assert port == ip_tag.port
            assert ip_tag.flags != 0

            # Clear the IPTag
            controller.iptag_clear(iptag)

            # Check that it is empty by inspecting the flag
            ip_tag = controller.iptag_get(iptag)
            assert ip_tag.flags == 0

    def test_led_on(self, controller):
        for x in range(2):
            for y in range(2):
                controller.set_led(1, x=x, y=y, action=True)

    def test_led_off(self, controller):
        for x in range(2):
            for y in range(2):
                controller.set_led(1, x=x, y=y, action=False)

    def test_led_toggle(self, controller):
        for _ in range(2):  # Toggle On -> Toggle Off
            for x in range(2):
                for y in range(2):
                    controller.set_led(1, x=x, y=y, action=None)

    def test_get_router_diagnostics(self, controller):
        # Get the router status of (1, 1) twice. Since doing this results in a
        # P2P SCP packet being sent from (0, 0) to (1, 1) the "local_p2p" in
        # (1, 1) register must be incremented.
        with controller(x=1, y=1):
            rd0 = controller.get_router_diagnostics()
            rd1 = controller.get_router_diagnostics()

        delta = rd1.local_p2p - rd0.local_p2p

        # Account for the possibility that the counter may wrap-around
        if delta < 0:  # pragma: no cover
            # Wrap-around appears to have ocurred. To be sure, check that the
            # delta is a large portion of the range of the counter's range (if
            # it isn't then the counter may well have gone backwards!).
            assert abs(delta) > (1 << 31)

            # Fix the wrap-around
            delta += 1 << 32
            assert delta >= 0  # Sanity check

        # If the read register command is really working, the counter should
        # definately have increased (since locally-arriving P2P packets are
        # sent in order to execute the command).
        assert delta >= 1

    def test_count_cores_in_state_idle(self, controller):
        """Check that we have no idle cores as there are no cores assigned to
        the application yet.
        """
        assert controller.count_cores_in_state("idle") == 0

    @pytest.mark.order_id("live_test_load_application")
    @pytest.mark.parametrize(
        "targets",
        [{(1, 1): {3, 4}, (1, 0): {5}},
         {(0, 1): {2}}]
    )
    def test_load_application(self, controller, targets):
        """Test loading an APLX.  The given APLX writes (x << 24) | (y << 16) |
        p into sdram_base + p*4; so we can check everything works by looking at
        that memory address.
        """
        assert isinstance(controller, MachineController)
        assert len(controller.structs) > 0, \
            "Controller has no structs, check test fixture."
        controller.load_application(
            pkg_resources.resource_filename("rig", "binaries/rig_test.aplx"),
            targets, use_count=False
        )

        # Read back a word and IOBUF to test that the application loaded
        for (t_x, t_y), cores in iteritems(targets):
            with controller(x=t_x, y=t_y):
                print(t_x, t_y)
                addr_base = controller.read_struct_field("sv", "sdram_base")

                for t_p in cores:
                    # Test memory location
                    addr = addr_base + 4 * t_p
                    data = struct.unpack(
                        "<I", controller.read(addr, 4, t_x, t_y)
                    )[0]
                    print(hex(data))
                    x = (data & 0xff000000) >> 24
                    y = (data & 0x00ff0000) >> 16
                    p = (data & 0x0000ffff)
                    assert p == t_p and x == t_x and y == t_y

                    # Test IOBUF contains expected message
                    assert controller.get_iobuf(t_p).startswith(
                        "Rig test APLX started on {}, {}, {}.\n".format(
                            t_x, t_y, t_p))

    @pytest.mark.order_after("live_test_load_application")
    @pytest.mark.parametrize(
        "all_targets",
        [{(1, 1): {3, 4}, (1, 0): {5}, (0, 1): {2}}]
    )
    def test_count_cores_in_state_run(self, controller, all_targets):
        expected = sum(len(cs) for cs in itervalues(all_targets))
        assert expected == controller.count_cores_in_state("run")

    @pytest.mark.order_after("live_test_load_application")
    @pytest.mark.parametrize(
        "targets",
        [{(1, 1): {3, 4}, (1, 0): {5}},
         {(0, 1): {2}}]
    )
    def test_get_processor_status(self, controller, targets):
        for (x, y), cores in iteritems(targets):
            with controller(x=x, y=y):
                for p in cores:
                    # Get the status and assert that the core is running, the
                    # app_id is correct and the cpu_state is fine.
                    status = controller.get_processor_status(p)
                    assert status.app_name == "rig_test"
                    assert status.cpu_state is consts.AppState.run
                    assert status.rt_code is consts.RuntimeException.none

    @pytest.mark.order_before("live_test_load_application")
    def test_get_system_info(self, live_system_info, spinnaker_width,
                             spinnaker_height):
        # Just check that the output is sane, doesn't verify that it is
        # actually correct. This test will fail if the target machine is very
        # dead...
        si = live_system_info

        # This test will fail if the system has dead chips on its periphery
        assert si.width == spinnaker_width
        assert si.height == spinnaker_height

        # Check that *most* chips aren't dead
        assert len(si) > (si.width * si.height) / 2

        # And *most* links aren't dead
        assert len(list(si.dead_links())) < (si.width * si.height * 6) / 2

        # Check that all working chips have a sensible number of working cores
        assert all(15 <= c.num_cores <= 18 for c in itervalues(si))

        # All cores should be idle, except the monitor
        assert all(c.core_states == ([consts.AppState.run] +
                                     ([consts.AppState.idle] *
                                      (c.num_cores - 1)))
                   for c in itervalues(si))

        # All cores should have nearly all of SDRAM available
        assert all(c.largest_free_sdram_block > 100 * 1024 * 1024
                   for c in itervalues(si))

        # All cores should have at least *some* SRAM available
        assert all(c.largest_free_sram_block > 0
                   for c in itervalues(si))

    def test_get_chip_info_spinn_5(self, controller, is_spinn_5_board):
        # We should be able to detect chip (0, 0) has only three working links
        chip_info = controller.get_chip_info(0, 0)
        assert 16 <= chip_info.num_cores <= 18
        assert chip_info.core_states[0] == consts.AppState.run
        assert (chip_info.core_states[1:] ==
                [consts.AppState.idle] * (chip_info.num_cores - 1))
        assert chip_info.working_links == set([
            Links.north,
            Links.north_east,
            Links.east,
        ])

    def test_get_system_info_spinn_5(self, live_system_info, spinnaker_width,
                                     spinnaker_height, is_spinn_5_board):
        # Verify get_machine in the special case when the attached machine is a
        # single SpiNN-5 or SpiNN-4 board. Verifies sanity of returned values.
        si = live_system_info
        nominal_live_chips = set([  # noqa
                                            (4, 7), (5, 7), (6, 7), (7, 7),
                                    (3, 6), (4, 6), (5, 6), (6, 6), (7, 6),
                            (2, 5), (3, 5), (4, 5), (5, 5), (6, 5), (7, 5),
                    (1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (7, 4),
            (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3), (7, 3),
            (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
            (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
            (0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
        ])

        # Check that the set of working chips is a subset of the above
        assert set(si).issubset(set(nominal_live_chips))

        # Check all links to chips out of the board are dead
        for link in Links:
            for (x, y) in nominal_live_chips:
                dx, dy = link.to_vector()
                neighbour = ((x + dx), (y + dy))
                if neighbour not in nominal_live_chips:
                    assert (x, y, link) not in si

    # NOTE: "Hello, SpiNNaker" is 4 words, it is important that one test is a
    # whole number of words and that another isn't.
    @pytest.mark.parametrize("data", [b"Hello, SpiNNaker",
                                      b"Bonjour SpiNNaker"])
    @pytest.mark.parametrize("clear", (False, True))
    def test_sdram_alloc_as_filelike_read_write(self, controller, data, clear):
        # Allocate some memory, write to it and check that we can read back
        with controller(x=1, y=0):
            mem = controller.sdram_alloc_as_filelike(len(data), clear=clear)

            # Check the memory was cleared if we requested it to be
            if clear:
                assert mem.read() == b'\x00' * len(data)

            # Write the data
            mem.seek(0)
            assert mem.write(data) == len(data)

            # Read back the data
            mem.seek(0)
            assert mem.read(len(data)) == data

    @pytest.mark.order_after("live_test_load_application")
    def test_get_chip_info(self, controller):
        # Just sanity check that the monitor processor is flagged as busy and 3
        # and 4 are too.
        with controller(x=1, y=1):
            chip_info = controller.get_chip_info()

            # Assuming a reasonably intact machine
            assert chip_info.num_cores in (17, 18)

            # No unexpected non-idle cores.
            assert chip_info.core_states == [  # pragma: no branch
                consts.AppState.run
                if c in (0, 3, 4) else
                consts.AppState.dead
                if c >= chip_info.num_cores else
                consts.AppState.idle
                for c in range(chip_info.num_cores)
            ]

            # All links should be alive (assuming an intact machine...)
            assert chip_info.working_links == set(Links)

            # Should have most SDRAM still available
            assert chip_info.largest_free_sdram_block > (100 * 1024 * 1024)

            # Should have some SRAM still available
            assert chip_info.largest_free_sdram_block > 0

            # If we allocate a 50 MB block of SDRAM the largest free block
            # should shrink accordingly
            controller.sdram_alloc(50 * 1024 * 1024)
            before = chip_info.largest_free_sdram_block
            after = controller.get_chip_info().largest_free_sdram_block
            assert (before - after) >= (50 * 1024 * 1024)

    @pytest.mark.order_id("live_test_load_routes")
    @pytest.mark.order_after("live_test_load_application")
    @pytest.mark.parametrize(
        "routes",
        [([RoutingTableEntry({Routes.east}, 0x0000ffff, 0xffffffff),
           RoutingTableEntry({Routes.west}, 0xffff0000, 0xffff0000)])
         ]
    )
    def test_load_and_retrieve_routing_tables(self, controller, routes):
        with controller(x=0, y=0):
            # Load the routing table entries
            controller.load_routing_table_entries(routes)

            # Retrieve the routing table entries and check that the ones we
            # loaded are present.
            loaded = controller.get_routing_table_entries()

        for entry in loaded:
            if entry is not None:
                (route, app_id, _) = entry
                assert app_id == 0 or route in routes

    @pytest.mark.order_after("live_test_load_application",
                             "live_test_load_routes")
    def test_app_stop_and_count(self, controller):
        controller.send_signal("stop")
        assert controller.count_cores_in_state("run") == 0

        # All the routing tables should have gone as well
        with controller(x=0, y=0):
            loaded = controller.get_routing_table_entries()

        for entry in loaded:
            if entry is not None:
                (_, app_id, _) = entry
                assert app_id == 0


class TestMachineController(object):
    """Test the machine controller against the ideal protocol.

        - Check that transmitted packets are sensible.
        - Check that error codes / correct returns are dealt with correctly.
    """
    def test_supplied_structs(self):
        """Check that when struct data is supplied, it is used."""
        structs = {
            b"test_struct": struct_file.Struct("test_struct", base=0xDEAD0000)}
        structs[b"test_struct"][b"test_field"] = \
            struct_file.StructField(b"I", 0x0000BEEF, "%d", 1234, 1)

        cn = MachineController("localhost", structs=structs)
        cn.read = mock.Mock()
        cn.read.return_value = b"\x01\x00\x00\x00"
        assert cn.read_struct_field("test_struct", "test_field", 0, 0, 0) == 1
        cn.read.assert_called_once_with(0xDEADBEEF, 4, 0, 0, 0)

    def test_send_scp(self):
        """Check that arbitrary SCP commands can be sent using the context
        system.
        """
        # Create the controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock(spec_set=[])

        # Assert a failure with no context
        with pytest.raises(TypeError):
            cn.send_scp(SCPCommands.sver, y=0, p=0)

        with pytest.raises(TypeError):
            cn.send_scp(SCPCommands.sver, x=0, p=0)

        with pytest.raises(TypeError):
            cn.send_scp(SCPCommands.sver, x=0, y=0)

        # Provide a context, should work
        with cn(x=3, y=2, p=0):
            cn.send_scp(SCPCommands.sver)
        cn._send_scp.assert_called_once_with(3, 2, 0, SCPCommands.sver)

        with cn(x=3, y=2, p=0):
            cn.send_scp(SCPCommands.sver, x=4)
        cn._send_scp.assert_called_with(4, 2, 0, SCPCommands.sver)

        with cn(x=3, y=2, p=0):
            cn.send_scp(SCPCommands.sver, y=4)
        cn._send_scp.assert_called_with(3, 4, 0, SCPCommands.sver)

        with cn(x=3, y=2, p=0):
            cn.send_scp(SCPCommands.sver, p=4)
        cn._send_scp.assert_called_with(3, 2, 4, SCPCommands.sver)

    @pytest.mark.parametrize("only_if_needed", [True, False])
    @pytest.mark.parametrize("check_booted", [True, False])
    @pytest.mark.parametrize("already_booted", [True, False])
    @pytest.mark.parametrize("boot_succeeds", [True, False])
    def test_boot(self, only_if_needed, check_booted, already_booted,
                  boot_succeeds, monkeypatch):
        """Make sure the 'smart' behaviour of the boot method works
        correctly.
        """
        # If the machine is already booted the boot cannot fail so this test
        # combination can be skipped since it makes no sense.
        if already_booted and not boot_succeeds:
            return

        working_core_info = CoreInfo(
            (0, 0), 0, 0, 1.3, 256, 0, "SpiNNaker Test")

        # Make a mock version of get_software_version which responds according
        # to the parameters of this test.
        get_software_version_responses = []
        if only_if_needed:
            # Respond to the first working_core_info request with a core info
            # if already booted, otherwise throw an SCPError as if the command
            # failed because the system was unbooted
            if already_booted:
                get_software_version_responses.append(working_core_info)
            else:
                get_software_version_responses.append(SCPError())
        if check_booted:
            # If we check for the working system we should return working core
            # info only if the boot succeeds
            if boot_succeeds:
                get_software_version_responses.append(working_core_info)
            else:
                get_software_version_responses.append(SCPError())
        mock_get_software_version = mock.Mock(
            side_effect=get_software_version_responses)
        monkeypatch.setattr(MachineController, "get_software_version",
                            mock_get_software_version)

        mc = MachineController("localhost")

        # The fake boot command should simply return some structs, in this case
        # the mock just hands back the structs already loaded by the
        # MachineController.
        mock_boot = mock.Mock(return_value=mc.structs)
        monkeypatch.setattr(boot, "boot", mock_boot)

        if boot_succeeds or not check_booted:
            did_boot = mc.boot(2, 4,
                               only_if_needed=only_if_needed,
                               check_booted=check_booted)

            # The machine should only get sent a boot command if it was not
            # already booted or we forced it
            assert did_boot == mock_boot.called
            assert did_boot == (not (already_booted and only_if_needed))
        else:
            # If the boot fails (and we checked) an exception should be thrown
            with pytest.raises(SpiNNakerBootError):
                mc.boot(2, 4,
                        only_if_needed=only_if_needed,
                        check_booted=check_booted)

        # If the machine should have been booted, make sure it was called with
        # the arguments we passed in
        if not (already_booted and only_if_needed):
            mock_boot.assert_called_once_with("localhost",
                                              boot_port=consts.BOOT_PORT,
                                              width=2, height=4)

        # Check the correct number of get_software_version calls are made
        if only_if_needed and check_booted and not already_booted:
            assert len(mock_get_software_version.mock_calls) == 2
        elif not (only_if_needed or check_booted):
            assert len(mock_get_software_version.mock_calls) == 0
        else:
            assert len(mock_get_software_version.mock_calls) == 1

    def test_boot_alien_machine(self, monkeypatch):
        """Make sure the boot command fails if you try to boot a BMP."""
        # Respond as if a BMP
        core_info = CoreInfo(
            (0, 0), 0, 0, 1.3, 256, 0, "BC&MP/Spin5-BMP\x00")

        mock_get_software_version = mock.Mock(return_value=core_info)
        monkeypatch.setattr(MachineController, "get_software_version",
                            mock_get_software_version)

        mc = MachineController("localhost")

        # Boot should fail due to already being booted as a BMP
        with pytest.raises(SpiNNakerBootError):
            mc.boot(2, 4)

    def test_get_software_version(self, mock_conn):  # noqa
        """Check that the reporting of the software version is correct.

        SCP Layout
        ----------
        The command code is: 0 "sver"
        There are no arguments.

        The returned packet is of form:
        arg1 : - p2p address in bits 31:16
               - physical CPU address in bits 15:8
               - virtual CPU address in bits 7:0
        arg2 : - version number * 100 in bits 31:16
               - buffer size (number of extra data bytes that can be included
                 in an SCP packet) in bits 15:0
        arg3 : build data in seconds since the Unix epoch.
        data : String encoding of build information.
        """
        # Create the machine controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = mock.Mock(spec_set=SCPPacket)
        cn._send_scp.return_value.arg1 = ((1 << 8 | 2) << 16) | (3 << 8) | 4
        cn._send_scp.return_value.arg2 = (256 << 16) | 256
        cn._send_scp.return_value.arg3 = 888999
        cn._send_scp.return_value.data = b"Hello, World!"

        # Run the software version command
        sver = cn.get_software_version(0, 1, 2)

        # Assert that the response is correct
        assert sver.position == (1, 2)
        assert sver.physical_cpu == 3
        assert sver.virt_cpu == 4
        assert sver.version == 2.56
        assert sver.buffer_size == 256
        assert sver.build_date == 888999
        assert sver.version_string == "Hello, World!"

    @pytest.mark.parametrize("has_ip", [True, False])
    def test_get_ip_address(self, has_ip):
        cn = MachineController("localhost")
        cn.read_struct_field = mock.Mock(side_effect=[has_ip, 0x11223344])

        ip = cn.get_ip_address(1, 2)

        if has_ip:
            assert ip == "68.51.34.17"
            cn.read_struct_field.assert_has_calls([
                mock.call("sv", "eth_up", x=1, y=2),
                mock.call("sv", "ip_addr", x=1, y=2),
            ])
        else:
            assert ip is None
            cn.read_struct_field.assert_called_once_with("sv", "eth_up",
                                                         x=1, y=2)

    def test__get_connection(self):
        cn = MachineController("localhost")
        cn.connections = {
            None: "default",
            (0, 0): "0,0",
            (4, 8): "4,8",
            # 8, 4 is missing!
        }

        # Until _width and _height are set, the default should be used at all
        # times.
        assert cn._get_connection(0, 0) == "default"
        assert cn._get_connection(1, 0) == "default"
        assert cn._get_connection(0, 1) == "default"
        assert cn._get_connection(11, 0) == "default"
        assert cn._get_connection(0, 11) == "default"

        # With width and height specified, the local connector should be used
        # in all cases when possible
        cn._width = 12
        cn._height = 12

        assert cn._get_connection(0, 0) == "0,0"
        assert cn._get_connection(1, 0) == "0,0"
        assert cn._get_connection(0, 1) == "0,0"

        assert cn._get_connection(4, 8) == "4,8"
        assert cn._get_connection(5, 8) == "4,8"
        assert cn._get_connection(4, 9) == "4,8"

        # When a missing a connection, another connection should be used
        assert cn._get_connection(8, 4) in ("default", "0,0", "4,8")
        assert cn._get_connection(9, 4) in ("default", "0,0", "4,8")
        assert cn._get_connection(8, 5) in ("default", "0,0", "4,8")

    def test_discover_connections(self):
        # In this test, the discovered system is a 6-board system with the
        # board with a dead chip on (16, 8), the Ethernet link at (4, 8) being
        # down, the connection to (8, 4) resulting in timeouts and the
        # connection to (20, 4) already present.
        cn = MachineController("localhost")
        w, h = 24, 12
        cn.get_p2p_routing_table = mock.Mock(return_value={
            (x, y): (consts.P2PTableEntry.north
                     if (x, y) != (16, 8) else
                     consts.P2PTableEntry.none)
            for x in range(w)
            for y in range(h)
        })

        def get_ip_address(x, y):
            if (x, y) == (4, 8):
                return None
            else:
                return "127.0.0.1"
        cn.get_ip_address = mock.Mock(side_effect=get_ip_address)

        def get_software_version(x, y):
            if (x, y) == (8, 4):
                raise SCPError("Fail.")
        cn.get_software_version = mock.Mock(side_effect=get_software_version)

        cn.connections[(20, 4)] = mock.Mock()

        assert cn.discover_connections() == 2
        assert cn._width == w
        assert cn._height == h
        assert set(cn.connections) == set([None, (0, 0), (12, 0), (20, 4)])
        assert isinstance(cn.connections[(0, 0)], SCPConnection)
        assert isinstance(cn.connections[(12, 0)], SCPConnection)

    @pytest.mark.parametrize("size", [128, 256])
    def test_scp_data_length(self, size):
        cn = MachineController("localhost")
        cn._scp_data_length = None
        cn.get_software_version = mock.Mock()
        cn.get_software_version.return_value = CoreInfo(
            None, None, None, None, size, None, None)

        assert cn.scp_data_length == size
        cn.get_software_version.assert_called_once_with(0, 0)

    @pytest.mark.parametrize(
        "buffer_size, window_size, x, y, p, start_address, data",
        [(128, 3, 0, 1, 2, 0x67800000, b"\x00" * 100),
         (256, 8, 1, 4, 5, 0x67801000, b"\x10\x23"),
         ]
    )
    def test_write(self, buffer_size, window_size, x, y, p,
                   start_address, data):
        # Create the mock controller
        cn = MachineController("localhost")
        cn._scp_data_length = buffer_size
        cn._window_size = window_size
        cn.connections[None] = mock.Mock(spec_set=SCPConnection)

        # Perform the read and ensure that values are passed on as appropriate
        with cn(x=x, y=y, p=p):
            cn.write(start_address, data)

        cn.connections[None].write.assert_called_once_with(
            buffer_size, window_size, x, y, p, start_address, data
        )

    @pytest.mark.parametrize(
        "buffer_size, window_size, x, y, p, start_address, length, data",
        [(128, 1, 0, 1, 2, 0x67800000, 100, b"\x00" * 100),
         (256, 5, 1, 4, 5, 0x67801000, 2, b"\x10\x23"),
         ]
    )
    def test_read(self, buffer_size, window_size, x, y, p,
                  start_address, length, data):
        # Create the mock controller
        cn = MachineController("localhost")
        cn._scp_data_length = buffer_size
        cn._window_size = window_size
        cn.connections[None] = mock.Mock(spec_set=SCPConnection)
        cn.connections[None].read.return_value = data

        # Perform the read and ensure that values are passed on as appropriate
        with cn(x=x, y=y, p=p):
            assert data == cn.read(start_address, length)

        cn.connections[None].read.assert_called_once_with(
            buffer_size, window_size, x, y, p, start_address, length
        )

    @pytest.mark.parametrize(
        "buffer_size, x, y, link, start_address, length, data",
        [(128, 0, 1, Links.north, 0x67800000, 80, [b"\x11" * 80, ]),
         (128, 2, 3, Links.south, 0x67800000, 152, [b"\x11" * 128,
                                                    b"\x22" * 24]),
         (256, 4, 5, Links.north, 0x67800000, 256, [b"\x11" * 256]),
         (256, 6, 7, Links.south, 0x67800000, 0, []),
         ]
    )
    def test_read_across_link(self, buffer_size, x, y, link,
                              start_address, length, data):
        # Create the mock controller
        cn = MachineController("localhost")
        cn._scp_data_length = buffer_size
        cn.connections[None] = mock.Mock(spec_set=SCPConnection)
        cn.connections[None].send_scp.side_effect = [mock.Mock(data=d)
                                                     for d in data]

        # Perform the read and ensure that values are passed on as appropriate
        # and the result is correct
        with cn(x=x, y=y, link=link):
            assert b"".join(data) == cn.read_across_link(start_address, length)

        # Should have one send_scp call per expected data block
        assert len(cn.connections[None].send_scp.mock_calls) == len(data)

        # The calls should be for the correct lengths etc.
        address = start_address
        for block, call in zip(data, cn.connections[None].send_scp.mock_calls):
            assert call[1][1] == x
            assert call[1][2] == y
            assert call[1][3] == 0
            assert call[1][4] == SCPCommands.link_read
            assert call[2]["arg1"] == address
            assert call[2]["arg2"] == len(block)
            assert call[2]["arg3"] == int(link)
            assert call[2]["expected_args"] == 0
            address += len(block)

    @pytest.mark.parametrize(
        "start_address, length",
        [(0x00000001, 4),
         (0x00000004, 1),
         (0x00000001, 1),
         ]
    )
    def test_read_across_link_unaligned(self, start_address, length):
        # Create the mock controller
        cn = MachineController("localhost")
        with pytest.raises(ValueError):
            cn.read_across_link(start_address, length,
                                x=0, y=0, link=Links.north)

    @pytest.mark.parametrize(
        "buffer_size, x, y, link, start_address, data",
        [(128, 0, 1, Links.north, 0x67800000, [b"\x11" * 80, ]),
         (128, 2, 3, Links.south, 0x67800000, [b"\x11" * 128, b"\x22" * 24]),
         (256, 4, 5, Links.north, 0x67800000, [b"\x11" * 256]),
         (256, 6, 7, Links.north, 0x67800000, []),
         ]
    )
    def test_write_across_link(self, buffer_size, x, y, link,
                               start_address, data):
        # Create the mock controller
        cn = MachineController("localhost")
        cn._scp_data_length = buffer_size
        cn.connections[None] = mock.Mock(spec_set=SCPConnection)

        # Perform the write of the complete data
        with cn(x=x, y=y, link=link):
            cn.write_across_link(start_address, b"".join(data))

        # Should have one send_scp call per expected data block
        assert len(cn.connections[None].send_scp.mock_calls) == len(data)

        # The calls should be for the correct lengths etc.
        address = start_address
        for block, call in zip(data, cn.connections[None].send_scp.mock_calls):
            assert call[1][1] == x
            assert call[1][2] == y
            assert call[1][3] == 0
            assert call[1][4] == SCPCommands.link_write
            assert call[2]["arg1"] == address
            assert call[2]["arg2"] == len(block)
            assert call[2]["arg3"] == int(link)
            assert call[2]["data"] == block
            assert call[2]["expected_args"] == 0
            address += len(block)

    @pytest.mark.parametrize(
        "start_address, data",
        [(0x00000001, b"\0" * 4),
         (0x00000004, b"\0" * 1),
         (0x00000001, b"\0" * 1),
         ]
    )
    def test_write_across_link_unaligned(self, start_address, data):
        # Create the mock controller
        cn = MachineController("localhost")
        with pytest.raises(ValueError):
            cn.write_across_link(start_address, data,
                                 x=0, y=0, link=Links.north)

    @pytest.mark.parametrize(
        "iptag, addr, port",
        [(1, "localhost", 54321),
         (3, "127.0.0.1", 65432),
         ])
    def test_iptag_set(self, iptag, addr, port):
        """Set an IPTag.

        Note: the hostnames picked here should *always* resolve to 127.0.0.1...

        SCP Layout
        ----------
        Outgoing:
            **Always to VCPU0!**
            cmd_rc : 26
            arg1 : 0x00010000 | iptag number
            arg2 : port
            arg3 : IP address (127.0.0.1 == 0x0100007f)
        """
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        # Set the IPTag
        cn.iptag_set(iptag, addr, port, x=0, y=1)

        # Assert that there was 1 packet sent and that it was sane
        assert cn._send_scp.call_count == 1
        call = cn._send_scp.call_args[0]
        assert call == (0, 1, 0, SCPCommands.iptag, 0x00010000 | iptag,
                        port, 0x0100007f)

    @pytest.mark.parametrize("iptag", [1, 2, 3])
    def test_iptag_get(self, iptag):
        """Check getting an IPTag.

        Outgoing:
            *Always to VCPU0!**
            cmd_rc : 26
            arg1 : 0x00020000 | iptag number
            arg2 : number of iptags to get (== 1)

        Incoming:
            cmd_rc : OK
            data : IPtag in form (4s 6s 3H I 2H B) ->
                   (ip, "max", port, timeout, flags, count, rx_port,
                    spin_addr, spin_port)

        The function returns a namedtuple containing the unpacked version of
        this data.
        """
        # Create an IPtag
        data = struct.pack("4s 6s 3H I 2H B", b"\x7f\x00\x00\x01", b""*6,
                           54321, 10, 0x11, 12, 13, 14, 15)

        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                              0x80, 0, 0, 0, 0, data)

        # Get the IPtag
        r_iptag = cn.iptag_get(iptag, x=1, y=2)

        # Assert that there was 1 packet sent and that it was sane
        assert cn._send_scp.call_count == 1
        call = cn._send_scp.call_args[0]
        assert call == (1, 2, 0, SCPCommands.iptag, 0x00020000 | iptag, 1)

        # Assert that the returned IPtag was as specified
        assert r_iptag.addr == "127.0.0.1"
        assert r_iptag.port == 54321
        assert r_iptag.timeout == 10
        assert r_iptag.flags == 0x11
        assert r_iptag.count == 12
        assert r_iptag.rx_port == 13
        assert r_iptag.spin_addr == 14
        assert r_iptag.spin_port == 15

    @pytest.mark.parametrize("iptag", [1, 2, 3])
    def test_iptag_clear(self, iptag):
        """Check clearing IPtags.

        Outgoing:
            **Always to VCPU0!**
            cmd_rc : 26
            arg1 : 0x0003 | iptag number
        """
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        # Clear the IPtag
        cn.iptag_clear(iptag, x=1, y=2)

        # Assert that there was 1 packet sent and that it was sane
        assert cn._send_scp.call_count == 1
        call = cn._send_scp.call_args[0]
        assert call == (1, 2, 0, SCPCommands.iptag, 0x00030000 | iptag)

    @pytest.mark.parametrize("action,led_action",
                             [(True, LEDAction.on), (False, LEDAction.off),
                              (None, LEDAction.toggle),
                              (None, LEDAction.toggle)])
    @pytest.mark.parametrize("x", [0, 1])
    @pytest.mark.parametrize("y", [0, 1])
    @pytest.mark.parametrize("led,leds", [(0, [0]), (1, [1]), ([2], [2]),
                                          ([0, 1, 2], [0, 1, 2])])
    def test_led_controls(self, action, led_action, x, y, led, leds):
        """Check setting/clearing/toggling an LED.

        Outgoing:
            cmd_rc : 25
            arg1 : (on | off | toggle) << (led * 2)
        """
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        # Perform the action
        cn.set_led(led, x=x, y=y, action=action)

        # Assert that there was 1 packet sent and that it was sane
        assert cn._send_scp.call_count == 1
        call, kwargs = cn._send_scp.call_args
        assert call == (x, y, 0, SCPCommands.led)
        assert kwargs["arg1"] == sum(led_action << (led * 2) for led in leds)

    @pytest.mark.parametrize("addr", [0x1, 0x4])
    @pytest.mark.parametrize("size", [3, 16])
    @pytest.mark.parametrize("data", [0x0, 0x2])
    @pytest.mark.parametrize("x, y, p", [(1, 2, 3), (7, 1, 9)])
    def test_fill(self, addr, size, data, x, y, p):
        """Check filling a region of memory."""
        # Create the mock controller
        cn = MachineController("localhost")

        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                              0x80, 0, addr, None, None, b"")
        cn.write = mock.Mock()

        # Perform the fill
        cn.fill(addr, data, size, x, y, p)

        if size % 4 or addr % 4:
            # If the size is not a whole number of words or is not word
            # aligned then use write to empty the memory
            cn.write.assert_called_once_with(
                addr, struct.pack("<B", data)*size, x, y, p)
        else:
            # Otherwise use FILL to clear the memory
            cn._send_scp.assert_any_call(x, y, p, 5, addr, data, size)

    @pytest.mark.parametrize("app_id", [30, 33])
    @pytest.mark.parametrize("size", [7, 8, 200])
    @pytest.mark.parametrize("tag", [0, 2])
    @pytest.mark.parametrize("addr", [0x1, 0x67000000, 0x61000000])
    @pytest.mark.parametrize("clear", (False, True))
    def test_sdram_alloc_success(self, app_id, size, tag, addr, clear):
        """Check allocating a region of SDRAM.

        Outgoing:
            cmd_rc : 28
            arg1 : app_id << 8 | op code (0)
            arg2 : size (bytes)
            arg3 : tag
        """
        # Create the mock controller
        cn = MachineController("localhost")

        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                              0x80, 0, addr, None, None, b"")
        cn.fill = mock.Mock()

        # Try the allocation
        x = 1
        y = 2
        address = cn.sdram_alloc(size, tag, x, y, app_id=app_id, clear=clear)

        # Check the return value
        assert address == addr

        # Check the packet was sent as expected
        cn._send_scp.assert_any_call(x, y, 0, 28, app_id << 8, size, tag)

        # If clear then check that write was called
        if clear:
            cn.fill.assert_called_once_with(addr, 0x0, size, x, y, 0)

    @pytest.mark.parametrize("x, y", [(1, 3), (5, 6)])
    @pytest.mark.parametrize("size, tag", [(8, 0), (200, 2)])
    def test_sdram_alloc_fail(self, x, y, size, tag):
        """Test that sdram_alloc raises an exception when ALLOC fails."""
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                              0x80, 0, 0, None, None, b"")
        cn.write = mock.Mock()

        with pytest.raises(SpiNNakerMemoryError) as excinfo:
            cn.sdram_alloc(size, tag=tag, x=x, y=y, app_id=30, clear=True)

        assert str((x, y)) in str(excinfo.value)
        assert str(size) in str(excinfo.value)

        if tag == 0:
            assert "tag" not in str(excinfo.value)
        else:
            assert "tag" in str(excinfo.value)
            assert str(tag) in str(excinfo.value)

        # NO write OR fill should have occurred
        assert cn._send_scp.call_count == 1  # No fill
        assert not cn.write.called  # No write

    @pytest.mark.parametrize(
        "x, y, app_id, tag, addr, size, buffer_size",
        [(0, 1, 30, 8, 0x67800000, 100, 20),
         (3, 4, 33, 2, 0x12134560, 300, 100)]
    )
    @pytest.mark.parametrize("clear", (True, False))
    def test_sdram_alloc_as_filelike(self, app_id, size, tag, addr, x, y,
                                     buffer_size, clear):
        """Test allocing and getting a file-like object returned."""
        # Create the mock controller
        cn = MachineController("localhost")
        cn.sdram_alloc = mock.Mock(return_value=addr)
        cn.write = mock.Mock()

        # Try the allocation
        fp = cn.sdram_alloc_as_filelike(size, tag, x, y, app_id=app_id,
                                        buffer_size=buffer_size, clear=clear)

        # Check that the arguments were passed on correctly
        cn.sdram_alloc.assert_called_once_with(size, tag, x, y, app_id, clear)

        # Check the fp has the expected start and end
        assert fp._start_address == addr
        assert fp._end_address == addr + size

        # Check the x and y are correct
        assert fp._machine_controller is cn
        assert fp._x == x
        assert fp._y == y

        # Check the buffer size
        assert fp.buffer_size == buffer_size

    @pytest.mark.parametrize("x, y, p", [(0, 1, 2), (2, 5, 6)])
    @pytest.mark.parametrize(
        "which_struct_ascii, field_ascii, expected",
        [("sv", "dbg_addr", 0),
         ("sv", "status_map", (0, )*20),
         ])
    def test_read_struct_field(self, x, y, p, which_struct_ascii, field_ascii,
                               expected):
        which_struct = six.b(which_struct_ascii)
        field = six.b(field_ascii)

        # Open the struct file
        struct_data = pkg_resources.resource_string("rig", "boot/sark.struct")
        structs = struct_file.read_struct_file(struct_data)
        assert (which_struct in structs and
                field in structs[which_struct]), "Test is broken"

        # Create the mock controller
        cn = MachineController("localhost")
        cn.structs = structs
        cn.read = mock.Mock()
        cn.read.return_value = b"\x00" * struct.calcsize(
            structs[which_struct][field].pack_chars) * \
            structs[which_struct][field].length

        # Perform the struct read
        with cn(x=x, y=y, p=p):
            returned = cn.read_struct_field(which_struct_ascii, field_ascii)
        assert returned == expected

        # Check that read was called appropriately
        cn.read.assert_called_once_with(
            structs[which_struct].base + structs[which_struct][field].offset,
            struct.calcsize(structs[which_struct][field].pack_chars *
                            structs[which_struct][field].length),
            x, y, p
        )

    @pytest.mark.parametrize("x, y, p", [(0, 1, 2), (2, 5, 6)])
    @pytest.mark.parametrize(
        "which_struct, field, value",
        [("sv", "dbg_addr", 5),
         ("sv", "status_map", (0, )*20),
         ])
    def test_write_struct_field(self, x, y, p, which_struct, field, value):
        # Open the struct file
        struct_data = pkg_resources.resource_string("rig", "boot/sark.struct")
        structs = struct_file.read_struct_file(struct_data)
        assert (six.b(which_struct) in structs and
                six.b(field) in structs[six.b(which_struct)]), "Test is broken"

        # Create the mock controller
        cn = MachineController("localhost")
        cn.structs = structs
        cn.write = mock.Mock()

        # Perform the struct write
        with cn(x=x, y=y, p=p):
            cn.write_struct_field(which_struct, field, value)

        which_struct = six.b(which_struct)
        field = six.b(field)
        if isinstance(value, tuple):
            bytes = struct.pack(
                b"<" + len(value) * structs[which_struct][field].pack_chars,
                *value
            )
        else:
            bytes = struct.pack(
                b"<" + structs[which_struct][field].pack_chars, value
            )

        # Check that read was called appropriately
        cn.write.assert_called_once_with(
            structs[which_struct].base + structs[which_struct][field].offset,
            bytes, x, y, p
        )

    @pytest.mark.parametrize("x, y, p, vcpu_base",
                             [(0, 0, 5, 0x67800000),
                              (1, 0, 5, 0x00000000),
                              (3, 2, 10, 0x00ff00ff)])
    @pytest.mark.parametrize(
        "field, data, converted",
        [("app_name", b"rig_test\x00\x00\x00\x00\x00\x00\x00\x00", "rig_test"),
         ("cpu_flags", b"\x08", 8)]
    )
    def test_read_vcpu_struct(self, x, y, p, vcpu_base, field, data,
                              converted):
        struct_data = pkg_resources.resource_string("rig", "boot/sark.struct")
        structs = struct_file.read_struct_file(struct_data)
        vcpu_struct = structs[b"vcpu"]
        assert six.b(field) in vcpu_struct, "Test is broken"
        field_ = vcpu_struct[six.b(field)]

        # Create a mock SV struct reader
        def mock_read_struct_field(struct_name, field, x, y, p=0):
            if six.b(struct_name) == b"sv" and six.b(field) == b"vcpu_base":
                return vcpu_base
            assert False, "Unexpected struct field read."  # pragma: no cover

        # Create the mock controller
        cn = MachineController("localhost")
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.side_effect = mock_read_struct_field
        cn.structs = structs
        cn.read = mock.Mock()
        cn.read.return_value = data

        # Perform the struct field read
        assert cn.read_vcpu_struct_field(field, x, y, p) == converted

        # Check that the VCPU base was used
        cn.read.assert_called_once_with(
            vcpu_base + vcpu_struct.size * p + field_.offset, len(data), x, y)

    @pytest.mark.parametrize("x, y, p, vcpu_base",
                             [(0, 0, 5, 0x67800000),
                              (1, 0, 5, 0x00000000),
                              (3, 2, 10, 0x00ff00ff)])
    @pytest.mark.parametrize(
        "field, value, data",
        [("app_name", "rig_test", b"rig_test\x00\x00\x00\x00\x00\x00\x00\x00"),
         ("cpu_flags", 8, b"\x08")]
    )
    def test_write_vcpu_struct(self, x, y, p, vcpu_base, field, value, data):
        struct_data = pkg_resources.resource_string("rig", "boot/sark.struct")
        structs = struct_file.read_struct_file(struct_data)
        vcpu_struct = structs[b"vcpu"]
        assert six.b(field) in vcpu_struct, "Test is broken"
        field_ = vcpu_struct[six.b(field)]

        # Create a mock SV struct reader
        def mock_read_struct_field(struct_name, field, x, y, p=0):
            if six.b(struct_name) == b"sv" and six.b(field) == b"vcpu_base":
                return vcpu_base
            assert False, "Unexpected struct field read."  # pragma: no cover

        # Create the mock controller
        cn = MachineController("localhost")
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.side_effect = mock_read_struct_field
        cn.structs = structs
        cn.write = mock.Mock()

        # Perform the struct field write
        cn.write_vcpu_struct_field(field, value, x, y, p)

        # Check that the VCPU base was used
        cn.write.assert_called_once_with(
            vcpu_base + vcpu_struct.size * p + field_.offset, data, x, y)

    @pytest.mark.parametrize("x, y, p, vcpu_base", [(0, 1, 11, 0x67801234),
                                                    (1, 4, 17, 0x33331110)])
    def test_get_processor_status(self, x, y, p, vcpu_base):
        struct_data = pkg_resources.resource_string("rig", "boot/sark.struct")
        structs = struct_file.read_struct_file(struct_data)
        vcpu_struct = structs[b"vcpu"]

        # Create a mock SV struct reader
        def mock_read_struct_field(struct_name, field, x, y, p=0):
            if six.b(struct_name) == b"sv" and six.b(field) == b"vcpu_base":
                return vcpu_base
            assert False, "Unexpected struct field read."  # pragma: no cover

        # Create the mock controller
        cn = MachineController("localhost")
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.side_effect = mock_read_struct_field
        cn.structs = structs
        cn.read = mock.Mock()

        # Create data to read for the processor status struct
        vcpu_struct.update_default_values(
            r0=0x00000000,
            r1=0x00000001,
            r2=0x00000002,
            r3=0x00000003,
            r4=0x00000004,
            r5=0x00000005,
            r6=0x00000006,
            r7=0x00000007,
            psr=0x00000008,
            sp=0x00000009,
            lr=0x0000000a,
            rt_code=int(consts.RuntimeException.api_startup_failure),
            cpu_flags=0x0000000c,
            cpu_state=int(consts.AppState.sync0),
            app_id=30,
            app_name=b"Hello World!\x00\x00\x00\x00",
        )
        cn.read.return_value = vcpu_struct.pack()

        # Get the processor status
        with cn(x=x, y=y, p=p):
            ps = cn.get_processor_status()

        # Assert that we asked for the vcpu_base
        cn.read_struct_field.assert_called_once_with("sv", "vcpu_base", x, y)

        # And that the read was from the correct location
        cn.read.assert_called_once_with(vcpu_base + vcpu_struct.size * p,
                                        vcpu_struct.size, x, y)

        # Finally, that the returned ProcessorStatus is sensible
        assert isinstance(ps, ProcessorStatus)
        assert ps.registers == [0, 1, 2, 3, 4, 5, 6, 7]
        assert ps.program_state_register == 8
        assert ps.stack_pointer == 9
        assert ps.link_register == 0xa
        assert ps.cpu_flags == 0xc
        assert ps.cpu_state is consts.AppState.sync0
        assert ps.app_id == 30
        assert ps.app_name == "Hello World!"
        assert ps.rt_code is consts.RuntimeException.api_startup_failure

    @pytest.mark.parametrize("_x, _y", [(0, 5), (7, 10)])
    @pytest.mark.parametrize("iobuf_addresses",
                             [[0x0],
                              [0xDEADBEEF, 0x0],
                              [0xDEADBEEF, 0x12345678, 0x0]])
    def test_get_iobuf(self, _x, _y, iobuf_addresses):
        # Check that a read is made from the right region of memory and that
        # the resulting data is unpacked correctly
        cn = MachineController("localhost")

        num_iobufs = len(iobuf_addresses) - 1

        iobuf_size = 0x1024

        def mock_read(address, length, x, y, p=0):
            assert x == _x
            assert y == _y
            assert p == 0
            assert address == iobuf_addresses.pop(0)
            assert length == iobuf_size + 16
            data = b"hello, world!\n"
            return (struct.pack("<4I",
                                iobuf_addresses[0],
                                0, 0,
                                len(data)) +
                    data +
                    (b"\0" * (length - 16 - len(data))))
        cn.read = mock.Mock(side_effect=mock_read)
        cn.read_struct_field = mock.Mock(return_value=iobuf_size)
        cn.read_vcpu_struct_field = mock.Mock(return_value=iobuf_addresses[0])

        # Get (and check) the IOBUF value
        with cn(x=_x, y=_y):
            assert cn.get_iobuf(1) == "hello, world!\n" * num_iobufs

    @pytest.mark.parametrize("_x, _y", [(0, 5), (7, 10)])
    def test_get_router_diagnostics(self, _x, _y):
        # Check that a read is made from the right region of memory and that
        # the resulting data is unpacked correctly
        cn = MachineController("localhost")

        def mock_read(address, length, x, y, p=0):
            assert x == _x
            assert y == _y
            assert p == 0
            assert address == 0xe1000300
            assert length == 64
            return struct.pack("<16I", *list(range(16)))
        cn.read = mock.Mock(side_effect=mock_read)

        # Get the router status
        with cn(x=_x, y=_y):
            rd = cn.get_router_diagnostics()

        # Assert this matches what we'd expect
        assert rd.local_multicast == 0
        assert rd.external_multicast == 1
        assert rd.local_p2p == 2
        assert rd.external_p2p == 3
        assert rd.local_nearest_neighbour == 4
        assert rd.external_nearest_neighbour == 5
        assert rd.local_fixed_route == 6
        assert rd.external_fixed_route == 7
        assert rd.dropped_multicast == 8
        assert rd.dropped_p2p == 9
        assert rd.dropped_nearest_neighbour == 10
        assert rd.dropped_fixed_route == 11
        assert rd.counter12 == 12
        assert rd.counter13 == 13
        assert rd.counter14 == 14
        assert rd.counter15 == 15

    @pytest.mark.parametrize("n_args", [0, 3])
    def test_flood_fill_aplx_args_fails(self, n_args):
        """Test that calling flood_fill_aplx with an invalid number of
        arguments raises a TypeError.
        """
        # Create the mock controller
        cn = MachineController("localhost")

        with pytest.raises(TypeError):
            cn.flood_fill_aplx(*([0] * n_args))

        with pytest.raises(TypeError):
            cn.load_application(*([0] * n_args))

    def test_get_next_nn_id(self):
        cn = MachineController("localhost")

        for i in range(1, 127):
            assert cn._get_next_nn_id() == 2*i
        assert cn._get_next_nn_id() == 2

    @pytest.mark.parametrize(
        "app_id, wait, cores",
        [(31, False, [1, 2, 3]), (12, True, [5]),
         (66, False, list(range(1, 18)))]
    )
    @pytest.mark.parametrize("present_map", [False, True])
    def test_flood_fill_aplx_single_aplx(self, cn, aplx_file, app_id, wait,
                                         cores, present_map):
        """Test loading a single APLX to a set of cores."""
        BASE_ADDRESS = 0x68900000
        # Create the mock controller
        cn._send_scp = mock.Mock()
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.return_value = BASE_ADDRESS

        # Target cores for APLX
        targets = {(0, 1): set(cores)}

        # Attempt to load
        with cn(app_id=app_id, wait=wait):
            if present_map:
                cn.flood_fill_aplx({aplx_file: targets})
            else:
                cn.flood_fill_aplx(aplx_file, targets)

        # Check the base address was retrieved
        cn.read_struct_field.assert_called_once_with("sv", "sdram_sys", 0, 0)

        # Determine the expected core mask
        coremask = 0x00000000
        for c in cores:
            coremask |= 1 << c

        # Read the aplx_data
        with open(aplx_file, "rb") as f:
            aplx_data = f.read()

        n_blocks = ((len(aplx_data) + cn._scp_data_length - 1) //
                    cn._scp_data_length)

        # Assert that the transmitted packets were sensible, do this by
        # decoding each call to send_scp.
        assert cn._send_scp.call_count == n_blocks + 2 + len(targets)
        # Flood-fill start
        (x, y, p, cmd, arg1, arg2, arg3) = cn._send_scp.call_args_list[0][0]
        assert x == y == p == 0
        assert cmd == SCPCommands.nearest_neighbour_packet
        op = (arg1 & 0xff000000) >> 24
        assert op == NNCommands.flood_fill_start
        blocks = (arg1 & 0x0000ff00) >> 8
        assert blocks == n_blocks

        assert arg2 == 0  # Used to be region now 0 to indicate that using FFCS

        assert arg3 & 0x80000000  # Assert that we allocate ID on SpiNNaker
        assert arg3 & 0x0000ff00 == NNConstants.forward << 8
        assert arg3 & 0x000000ff == NNConstants.retry

        # Flood fill core select
        (x, y, p, cmd, arg1, arg2, arg3) = cn._send_scp.call_args_list[1][0]

        assert x == y == p == 0
        assert cmd == SCPCommands.nearest_neighbour_packet
        op = (arg1 & 0xff000000) >> 24
        assert op == NNCommands.flood_fill_core_select
        cores = arg1 & 0x0003ffff
        assert cores == coremask

        assert arg2 == regions.get_region_for_chip(0, 1, level=3)

        assert arg3 & 0x0000ff00 == NNConstants.forward << 8
        assert arg3 & 0x000000ff == NNConstants.retry

        # Flood fill data
        address = BASE_ADDRESS
        for n in range(0, n_blocks):
            # Get the next block of data
            (block_data, aplx_data) = (aplx_data[:cn._scp_data_length],
                                       aplx_data[cn._scp_data_length:])

            # Check the sent SCP packet
            (x_, y_, p_, cmd, arg1, arg2, arg3, data) = \
                cn._send_scp.call_args_list[n+2][0]

            # Assert the x, y and p are the same
            assert x_ == x and y_ == y and p_ == p

            # Arguments
            assert cmd == SCPCommands.flood_fill_data
            assert arg1 & 0xff000000 == NNConstants.forward << 24
            assert arg1 & 0x00ff0000 == NNConstants.retry << 16
            assert arg2 & 0x00ff0000 == (n << 16)
            assert arg2 & 0x0000ff00 == (len(data) // 4 - 1) << 8
            assert arg3 == address
            assert data == block_data

            # Progress address
            address += len(data)

        # Flood fill end
        (x_, y_, p_, cmd, arg1, arg2, arg3) = \
            cn._send_scp.call_args_list[-1][0]
        assert x_ == x and y_ == y and p_ == p
        assert cmd == SCPCommands.nearest_neighbour_packet
        assert arg1 & 0xff000000 == NNCommands.flood_fill_end << 24
        assert arg2 & 0xff000000 == app_id << 24
        assert arg2 & 0x0003ffff == 0  # 0 because we're using FFCS

        exp_flags = 0x00000000
        if wait:
            exp_flags |= consts.AppFlags.wait
        assert arg2 & 0x00fc0000 == exp_flags << 18

    def test_flood_fill_aplx_ordered_regions(self, cn, aplx_file):
        """Test that flood-fill regions and core masks are sent in ascending
        order.
        """
        BASE_ADDRESS = 0x68900000
        # Create the mock controller
        cn._send_scp = mock.Mock()
        cn.read_struct_field = mock.Mock(return_value=BASE_ADDRESS)

        # Override _send_ffcs such that it ensures increasing values of
        # ((region << 18) | cores)
        class SendFFCS(object):
            def __init__(self):
                self.last_sent = 0

            def __call__(self, region, cores, fr):
                # Create the ID for the packet
                x = (region << 18) | cores
                assert x > self.last_sent
                self.last_sent = x

        cn._send_ffcs = mock.Mock(side_effect=SendFFCS())

        # Empty targets because we'll override "compress_flood_fill_regions" to
        # return values out-of-order.
        targets = dict()
        regions_cores = [(100, 2), (100, 1), (10, 3)]

        # Attempt to load
        with mock.patch("rig.machine_control.machine_controller.regions."
                        + "compress_flood_fill_regions") as cffr:
            # Set the targets
            cffr.return_value = iter(regions_cores)

            # Perform the flood fille
            cn.flood_fill_aplx({aplx_file: targets})

        assert cn._send_ffcs.call_count == len(regions_cores)

    def test_load_and_check_succeed_use_count(self):
        """Test that APLX loading doesn't take place multiple times if the core
        count comes back good.
        """
        # Construct the machine controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn.count_cores_in_state = mock.Mock()
        cn.flood_fill_aplx = mock.Mock()
        cn.read_vcpu_struct_field = mock.Mock()
        cn.send_signal = mock.Mock()

        # Construct a list of targets and a list of failed targets
        app_id = 27
        targets = {
            "spam": {(0, 0): set([0, 1, 2]),
                     (1, 1): set([1])},
            "eggs": {(2, 3): set([4, 5, 6])}
        }

        def count_cores_in_state(state, id_):
            assert state == "wait"
            assert id_ == app_id
            return 7  # NO cores failed!
        cn.count_cores_in_state.side_effect = count_cores_in_state

        # Test that loading applications results in calls to flood_fill_aplx,
        # and read_struct_field and that failed cores are reloaded.
        with cn(app_id=app_id):
            cn.load_application(targets, wait=True, use_count=True)

        # First and second loads
        cn.flood_fill_aplx.assert_has_calls([
            mock.call(targets, app_id=app_id, wait=True),
        ])

        # Check that count cores was called and that read__vcpu_struct wasn't!
        assert cn.count_cores_in_state.called
        assert not cn.read_vcpu_struct_field.called

        # No signals sent
        assert not cn.send_signal.called

    @pytest.mark.parametrize("use_count", [True, False])
    def test_load_and_check_aplxs(self, use_count):
        """Test that APLX loading takes place multiple times if one of the
        chips fails to be placed in the wait state.
        """
        # Construct the machine controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn.count_cores_in_state = mock.Mock()
        cn.flood_fill_aplx = mock.Mock()
        cn.read_vcpu_struct_field = mock.Mock()
        cn.send_signal = mock.Mock()

        # Construct a list of targets and a list of failed targets
        app_id = 27
        targets = {(0, 1): {2, 4}}
        failed_targets = {(0, 1, 4)}
        faileds = {(0, 1): {4}}

        def count_cores_in_state(state, id_):
            assert state == "wait"
            assert id_ == app_id
            return 1  # 1 core safely loaded
        cn.count_cores_in_state.side_effect = count_cores_in_state

        def read_struct_field(fn, x, y, p):
            assert cn.count_cores_in_state.called is use_count

            if (x, y, p) in failed_targets:
                failed_targets.remove((x, y, p))  # Succeeds next time
                return consts.AppState.idle
            else:
                return consts.AppState.wait
        cn.read_vcpu_struct_field.side_effect = read_struct_field

        # Test that loading applications results in calls to flood_fill_aplx,
        # and read_struct_field and that failed cores are reloaded.
        with cn(app_id=app_id):
            cn.load_application("test.aplx", targets,
                                use_count=use_count, wait=True)

        # First and second loads
        cn.flood_fill_aplx.assert_has_calls([
            mock.call({"test.aplx": targets}, app_id=app_id, wait=True),
            mock.call({"test.aplx": faileds}, app_id=app_id, wait=True),
        ])

        # Reading struct values
        cn.read_vcpu_struct_field.assert_has_calls([
            mock.call("cpu_state", x, y, p)
            for (x, y), ps in iteritems(targets) for p in ps
        ] + [
            mock.call("cpu_state", x, y, p)
            for (x, y), ps in iteritems(faileds) for p in ps
        ])

        # No signals sent
        assert not cn.send_signal.called

    def test_load_and_check_aplxs_no_wait(self):
        """Test that APLX loading takes place multiple times if one of the
        chips fails to be placed in the wait state.
        """
        # Construct the machine controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn.flood_fill_aplx = mock.Mock()
        cn.read_vcpu_struct_field = mock.Mock()
        cn.send_signal = mock.Mock()

        # Construct a list of targets and a list of failed targets
        app_id = 27
        targets = {(0, 1): {2, 4}}
        failed_targets = {(0, 1, 4)}
        faileds = {(0, 1): {4}}

        def read_struct_field(fn, x, y, p):
            if (x, y, p) in failed_targets:
                failed_targets.remove((x, y, p))  # Succeeds next time
                return consts.AppState.idle
            else:
                return consts.AppState.wait
        cn.read_vcpu_struct_field.side_effect = read_struct_field

        # Test that loading applications results in calls to flood_fill_aplx,
        # and read_struct_field and that failed cores are reloaded.
        with cn(app_id=app_id):
            cn.load_application({"test.aplx": targets}, use_count=False)

        # First and second loads
        cn.flood_fill_aplx.assert_has_calls([
            mock.call({"test.aplx": targets}, app_id=app_id, wait=True),
            mock.call({"test.aplx": faileds}, app_id=app_id, wait=True),
        ])

        # Reading struct values
        cn.read_vcpu_struct_field.assert_has_calls([
            mock.call("cpu_state", x, y, p)
            for (x, y), ps in iteritems(targets) for p in ps
        ] + [
            mock.call("cpu_state", x, y, p)
            for (x, y), ps in iteritems(faileds) for p in ps
        ])

        # Start signal sent
        cn.send_signal.assert_called_once_with("start", app_id)

    def test_load_and_check_aplxs_fails(self):
        """Test that APLX loading takes place multiple times if one of the
        chips fails to be placed in the wait state.
        """
        # Construct the machine controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn.flood_fill_aplx = mock.Mock()
        cn.read_vcpu_struct_field = mock.Mock()
        cn.send_signal = mock.Mock()

        # Construct a list of targets and a list of failed targets
        app_id = 27
        targets = {(0, 1): {2, 4}}
        failed_targets = {(0, 1, 4)}

        def read_struct_field(fn, x, y, p):
            if (x, y, p) in failed_targets:
                return consts.AppState.idle
            else:
                return consts.AppState.wait
        cn.read_vcpu_struct_field.side_effect = read_struct_field

        # Test that loading applications results in calls to flood_fill_aplx,
        # and read_struct_field and that failed cores are reloaded.
        with cn(app_id=app_id):
            with pytest.raises(SpiNNakerLoadingError) as excinfo:
                cn.load_application({"test.aplx": targets}, use_count=False)

        assert "(0, 1, 4)" in str(excinfo.value)

    @pytest.mark.parametrize("signal", ["non-existant",
                                        consts.AppDiagnosticSignal.AND])
    def test_send_signal_fails(self, signal):
        # Make sure that the send_signal function rejects bad signal
        # identifiers (or ones that require special treatment)
        cn = MachineController("localhost")
        with pytest.raises(ValueError):
            cn.send_signal(signal)

    @pytest.mark.parametrize("app_id", [16, 30])
    @pytest.mark.parametrize("signal,expected_signal_num",
                             [(consts.AppSignal.sync0, consts.AppSignal.sync0),
                              (consts.AppSignal.timer, consts.AppSignal.timer),
                              (consts.AppSignal.start, consts.AppSignal.start),
                              ("sync0", consts.AppSignal.sync0),
                              ("timer", consts.AppSignal.timer),
                              ("start", consts.AppSignal.start)])
    def test_send_signal_one_target(self, app_id, signal, expected_signal_num):
        # Create the controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        # Send the signal
        with cn(app_id=app_id):
            cn.send_signal(signal)

        # Check an appropriate packet was sent
        assert cn._send_scp.call_count == 1
        cargs = cn._send_scp.call_args[0]
        assert cargs[:3] == (0, 0, 0)  # x, y, p

        (cmd, arg1, arg2, arg3) = cargs[3:8]
        assert cmd == SCPCommands.signal
        assert arg1 == consts.signal_types[expected_signal_num]
        assert arg2 & 0x000000ff == app_id
        assert arg2 & 0x0000ff00 == 0xff00  # App mask for 1 app_id
        assert arg2 & 0x00ff0000 == expected_signal_num << 16
        assert arg3 == 0x0000ffff  # Transmit to all

    # XXX: This is here ONLY until SpiNNaker tools 1.4!!!
    def test_send_signal_stop_clears_routing_table_entries(self):
        _app_id = 43

        # Calling `send_signal("stop")` and friends should ask for a machine
        # object and clear the routing tables on all extant chips.
        # Create a mock machine with some dead cores
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        si = SystemInfo(5, 4, {
            (x, y): ChipInfo(
                num_cores=0,
                core_states=[],
                working_links=set(),
                largest_free_sdram_block=0,
                largest_free_sram_block=0)
            for x in range(5)
            for y in range(4)
            if (x, y) not in [(0, 1), (1, 0), (1, 1)]
        })
        cn.get_system_info = mock.Mock(return_value=si)

        def clear_routing_table_fn(x, y, app_id):
            assert app_id == _app_id
            assert (x, y) in si

        cn.clear_routing_table_entries = mock.Mock()
        cn.clear_routing_table_entries.side_effect = clear_routing_table_fn

        # Send stop and assert that the routing table entries are removed apart
        # from where a dead chip is located.
        with cn(app_id=_app_id):
            cn.send_signal("stop")
        assert cn.clear_routing_table_entries.call_count == 20 - 3

    @pytest.mark.parametrize("app_id, count", [(16, 3), (30, 68)])
    @pytest.mark.parametrize("state, expected_state_num",
                             [(consts.AppState.idle, consts.AppState.idle),
                              (consts.AppState.run, consts.AppState.run),
                              ("idle", consts.AppState.idle),
                              ("run", consts.AppState.run)])
    def test_count_cores_in_state(self, app_id, count,
                                  state, expected_state_num):
        # Create the controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = mock.Mock(spec_set=SCPPacket)
        cn._send_scp.return_value.arg1 = count

        # Count the cores
        with cn(app_id=app_id):
            assert cn.count_cores_in_state(state) == count

        # Check an appropriate packet was sent
        assert cn._send_scp.call_count == 1
        cargs = cn._send_scp.call_args[0]
        assert cargs[:3] == (0, 0, 0)  # x, y, p

        (cmd, arg1, arg2, arg3) = cargs[3:8]
        assert cmd == SCPCommands.signal
        assert (
            arg1 ==
            consts.diagnostic_signal_types[consts.AppDiagnosticSignal.count]
        )

        # level | op | mode | state | app_mask | app_id
        assert arg2 & 0x000000ff == app_id
        assert arg2 & 0x0000ff00 == 0xff00  # App mask for 1 app_id
        assert arg2 & 0x000f0000 == expected_state_num << 16
        assert arg2 & 0x00300000 == consts.AppDiagnosticSignal.count << 20
        assert arg2 & 0x03c00000 == 1 << 22  # op == 1
        assert arg2 & 0x0c000000 == 0  # level == 0
        assert arg3 == 0x0000ffff  # Transmit to all

    @pytest.mark.parametrize(
        "states, exp", [(("idle", "exit"), 4),
                        (["runtime_exception", "watchdog", "dead"], 6)]
    )
    def test_count_cores_in_state_iterable_of_states(self, states, exp):
        # Create the controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = mock.Mock(spec_set=SCPPacket)
        cn._send_scp.return_value.arg1 = 2

        # Count the cores
        assert cn.count_cores_in_state(states) == exp

        # Check the correct number of packets were sent
        assert cn._send_scp.call_count == len(states)

    @pytest.mark.parametrize("state", ["non-existant",
                                       consts.AppDiagnosticSignal.AND])
    def test_count_cores_in_state_fails(self, state):
        # Make sure that the count_cores_in_state function rejects bad state
        # identifiers (or ones that require special treatment)
        cn = MachineController("localhost")
        with pytest.raises(ValueError):
            cn.count_cores_in_state(state)

    @pytest.mark.parametrize("app_id, count", [(16, 3), (30, 68)])
    @pytest.mark.parametrize("n_tries", [1, 3])
    @pytest.mark.parametrize("timeout", [None, 1.0])
    @pytest.mark.parametrize("excess", [True, False])
    @pytest.mark.parametrize("state", [consts.AppState.idle, "run"])
    def test_wait_for_cores_to_reach_state(self, app_id, count, n_tries,
                                           timeout, excess, state):
        # Create the controller
        cn = MachineController("localhost")

        # The count_cores_in_state mock will return less than the required
        # number of cores the first n_tries attempts and then start returning a
        # suffient number of cores.
        cn.count_cores_in_state = mock.Mock()
        n_tries_elapsed = [0]

        def count_cores_in_state(state_, app_id_):
            assert state_ == state
            assert app_id_ == app_id

            if n_tries_elapsed[0] < n_tries:
                n_tries_elapsed[0] += 1
                return count - 1
            else:
                if excess:
                    return count + 1
                else:
                    return count
        cn.count_cores_in_state.side_effect = count_cores_in_state

        val = cn.wait_for_cores_to_reach_state(state, count, app_id,
                                               0.001, timeout)
        if excess:
            assert val == count + 1
        else:
            assert val == count

        assert n_tries_elapsed[0] == n_tries

    def test_wait_for_cores_to_reach_state_timeout(self):
        # Create the controller
        cn = MachineController("localhost")

        cn.count_cores_in_state = mock.Mock()
        cn.count_cores_in_state.return_value = 0

        time_before = time.time()
        val = cn.wait_for_cores_to_reach_state("sync0", 10, 30, 0.01, 0.05)
        time_after = time.time()

        assert val == 0

        # The timeout interval should have at least occurred
        assert (time_after - time_before) >= 0.05

        # At least two attempts should have been possible in that time
        assert len(cn.count_cores_in_state.mock_calls) >= 2

        for call in cn.count_cores_in_state.mock_calls:
            assert call == mock.call("sync0", 30)

    @pytest.mark.parametrize("x, y, app_id", [(1, 2, 32), (4, 10, 17)])
    @pytest.mark.parametrize(
        "entries",
        [[RoutingTableEntry({Routes.east}, 0xffff0000, 0xffff0000),
          RoutingTableEntry({Routes.west}, 0xfffc0000, 0xfffff000),
          RoutingTableEntry({Routes.north_east}, 0xfffc0000, 0xfffff000)],
         ]
    )
    @pytest.mark.parametrize("base_addr, rtr_base", [(0x67800000, 3)])
    def test_load_routing_table_entries(self, x, y, app_id, entries,
                                        base_addr, rtr_base):
        # Create the controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(
            False, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0x80, 0x80, rtr_base,
            None, None, b""
        )

        # Allow writing to a file
        temp_mem = tempfile.TemporaryFile()
        cn.write = mock.Mock()
        cn.write.side_effect = lambda addr, data, x, y: temp_mem.write(data)

        # Allow reading the struct field
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.return_value = base_addr

        # Try the load
        with cn(x=x, y=y, app_id=app_id):
            cn.load_routing_table_entries(entries)

        # Try loading some routing table entries, this should cause
        # (1) Request for the table entries
        cn._send_scp.assert_any_call(
            x, y, 0, SCPCommands.alloc_free,
            (app_id << 8) | consts.AllocOperations.alloc_rtr,
            len(entries)
        )

        # (2) Request for the "sv" "sdram_sys" value
        cn.read_struct_field.assert_called_once_with("sv", "sdram_sys", x, y)

        # (3) A write to this address of the routing table entries
        temp_mem.seek(0)
        rte_data = temp_mem.read()
        i = 0
        while len(rte_data) > 0:
            entry_data, rte_data = rte_data[:16], rte_data[16:]
            next, free, route, key, mask = struct.unpack("<2H 3I", entry_data)

            assert next == i
            assert free == 0
            assert key == entries[i].key and mask == entries[i].mask

            exp_route = 0x00000000
            for r in entries[i].route:
                exp_route |= 1 << r

            assert exp_route == route
            i += 1

        # (4) A call to RTR_LOAD
        cn._send_scp.assert_called_with(
            x, y, 0, SCPCommands.router,
            ((len(entries) << 16) | (app_id << 8) |
             consts.RouterOperations.load),
            base_addr, rtr_base
        )

    def test_load_routing_table_entries_fails(self):
        # Create the controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(
            False, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0x80, 0x0, 0,
            None, None, b""
        )  # Indicates NO space for entries

        with pytest.raises(SpiNNakerRouterError) as excinfo:
            cn.load_routing_table_entries([None] * 100, 0, 4, 32)
        assert "100" in str(excinfo.value)
        assert "(0, 4)" in str(excinfo.value)

    @pytest.mark.parametrize(
        "routing_tables",
        [{(0, 1): [RoutingTableEntry({Routes.core_1}, 0x00ff0000, 0xffff0000)],
          (1, 1): [RoutingTableEntry({Routes.east}, 0x00ff0000, 0xffff0000)],
          }])
    def test_loading_routing_tables(self, routing_tables):
        cn = MachineController("localhost")
        cn.load_routing_table_entries = mock.Mock()

        # Load the set of routing table entries
        with cn(app_id=69):
            cn.load_routing_tables(routing_tables)

        # Check all the calls were made
        cn.load_routing_table_entries.assert_has_calls(
            [mock.call(entries, x=x, y=y, app_id=69)
             for (x, y), entries in iteritems(routing_tables)]
        )

    @pytest.mark.parametrize("x, y", [(0, 1), (50, 32)])
    @pytest.mark.parametrize(
        "addr, data, expected",
        [(0x67090000,
          b"\x00\x00\x42\x03\x01\x00\x00\x00\x55\x55\xff\xff\xff\xff\xff\xff" +
          b"\xff" * 1023 * 16,
          [(RoutingTableEntry({Routes.east}, 0xffff5555, 0xffffffff), 66, 3)] +
          [None] * 1023
          ),
         (0x63090000,
          b"\xff" * 16 +
          b"\x00\x00\x42\x03\x01\x00\x00\x00\x55\x55\xff\xff\xff\xff\xff\xff" +
          b"\xff" * 1022 * 16,
          [None] +
          [(RoutingTableEntry({Routes.east}, 0xffff5555, 0xffffffff), 66, 3)] +
          [None] * 1022
          ),
         (0x67040000, b"\xff" * 1024 * 16, [None] * 1024),
         ]
    )
    def test_get_routing_table_entries(self, x, y, addr, data, expected):
        # Create the controller
        cn = MachineController("localhost")
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.return_value = addr
        cn.read = mock.Mock()
        cn.read.return_value = data

        # Read a routing table, assert that the return values are sane and that
        # appropriate calls are made.
        with cn(x=x, y=y):
            assert cn.get_routing_table_entries() == expected

        cn.read_struct_field.assert_called_once_with("sv", "rtr_copy", x, y)
        cn.read.assert_called_once_with(addr, 1024*16, x, y)

    @pytest.mark.parametrize("x, y, app_id", [(0, 1, 65), (3, 2, 55)])
    def test_clear_routing_table_entries(self, x, y, app_id):
        # Create the controller to ensure that appropriate packets are sent
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        # Clear the routing table entries
        with cn(app_id=app_id, x=x, y=y):
            cn.clear_routing_table_entries()

        # Assert ONE packet was sent to do this
        arg1 = (app_id << 8) | consts.AllocOperations.free_rtr_by_app
        arg2 = 1
        cn._send_scp.assert_called_once_with(x, y, 0, SCPCommands.alloc_free,
                                             arg1, arg2)

    def test_get_p2p_routing_table(self):
        cn = MachineController("localhost")

        # Pretend this is a 10x15 machine
        w, h = 10, 15

        def read_struct_field(struct, field, x, y):
            assert struct == "sv"
            assert field == "p2p_dims"
            assert x == 0
            assert y == 0
            return (w << 8) | h
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.side_effect = read_struct_field

        p2p_table_len = ((256*256)//8*4)
        reads = set()

        def read(addr, length, x, y):
            assert consts.SPINNAKER_RTR_P2P <= addr
            assert addr < consts.SPINNAKER_RTR_P2P + p2p_table_len
            assert length == (((h + 7) // 8) * 4)
            assert x == 0
            assert y == 0
            reads.add(addr)
            return (struct.pack("<I", sum(i << 3 * i for i in range(8))) *
                    (length // 4))
        # Return one of each kind of table entry per word for each read
        cn.read = mock.Mock()
        cn.read.side_effect = read

        p2p_table = cn.get_p2p_routing_table(x=0, y=0)

        # Should have done one table read per column
        assert set(consts.SPINNAKER_RTR_P2P + ((x * 256) // 8 * 4)
                   for x in range(w)) == reads

        # Check that the table is complete
        assert (set(p2p_table) ==  # pragma: no branch
                set((x, y) for x in range(w) for y in range(h)))

        # Check that every entry is correct.
        for (x, y), entry in iteritems(p2p_table):
            word_offset = y % 8
            desired_entry = consts.P2PTableEntry(word_offset)
            assert entry == desired_entry

    @pytest.mark.parametrize("links", [set(),
                                       set([Links.north, Links.south]),
                                       set(Links)])
    def test_get_working_links(self, links):
        cn = MachineController("localhost")
        cn.get_chip_info = mock.Mock()
        cn.get_chip_info.return_value = mock.Mock(working_links=links)

        assert cn.get_working_links(x=1, y=2) == links

        cn.get_chip_info.assert_called_once_with(1, 2)

    @pytest.mark.parametrize("num_cpus", [1, 18])
    def test_get_num_working_cores(self, num_cpus):
        cn = MachineController("localhost")
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.return_value = num_cpus

        assert cn.get_num_working_cores(x=0, y=0) == num_cpus
        cn.read_struct_field.assert_called_once_with("sv", "num_cpus", 0, 0)

    @pytest.mark.parametrize("arg1,num_cores,working_links",
                             [((18 | (0b111110 << 8)),
                               18,
                               set(l for l in Links if l != Links.east)),
                              ((18 | (0b011111 << 8)),
                               18,
                               set(l for l in Links if l != Links.south)),
                              ((17 | (0b111111 << 8)),
                               17,
                               set(Links)),
                              ])
    @pytest.mark.parametrize("arg2,largest_free_sdram_block",
                             [(1024, 1024), (0xFFFFFFFF, 0xFFFFFFFF)])
    @pytest.mark.parametrize("arg3,largest_free_sram_block",
                             [(1024, 1024), (0xFFFFFFFF, 0xFFFFFFFF)])
    def test_get_chip_info(self, arg1, num_cores, working_links,
                           arg2, largest_free_sdram_block,
                           arg3, largest_free_sram_block):

        core_states = [s for s, _ in zip(itertools.cycle(consts.AppState),
                                         range(num_cores))]

        data = struct.pack("<18B", *(core_states + ([0] * (18 - num_cores))))

        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = mock.Mock(arg1=arg1, arg2=arg2, arg3=arg3,
                                              data=data)

        chip_info = cn.get_chip_info(1, 2)

        cn._send_scp.assert_called_once_with(1, 2, 0,
                                             SCPCommands.info,
                                             expected_args=3)

        assert chip_info.num_cores == num_cores
        assert chip_info.core_states == core_states
        assert chip_info.working_links == working_links
        assert chip_info.largest_free_sdram_block == largest_free_sdram_block
        assert chip_info.largest_free_sram_block == largest_free_sram_block

    def test_get_system_info(self):
        cn = MachineController("localhost")

        # Return a set of p2p tables where an 10x8 set of chips is alive with
        # all except (0, 1) being dead.
        cn.get_p2p_routing_table = mock.Mock()
        cn.get_p2p_routing_table.return_value = {
            (x, y): (consts.P2PTableEntry.north
                     if x < 10 and y < 8 and (x, y) != (0, 1) else
                     consts.P2PTableEntry.none)
            for x in range(256)
            for y in range(256)
        }

        # Return some value except for (2, 3) which will produce an error.
        # Make each info unique by setting the largest_free_sdram_block to a
        # function of its x and y for later checking.

        def get_chip_info(x, y):
            assert (x, y) != (0, 1)
            if (x, y) == (2, 3):
                raise SCPError()
            else:
                return ChipInfo(
                    num_cores=18,
                    core_states=[consts.AppState.idle for _ in range(18)],
                    working_links=set(Links),
                    largest_free_sdram_block=0xFF0000 | (x << 8) | y,
                    largest_free_sram_block=(x << 8) | y,
                )
        cn.get_chip_info = mock.Mock(side_effect=get_chip_info)

        system_info = cn.get_system_info(2, 1)

        # Check dimensions
        assert system_info.width == 10
        assert system_info.height == 8

        # Two dead chips
        assert set(system_info.dead_chips()) == set([(0, 1), (2, 3)])

        # Check the correct info is associated with each...
        assert all(info.largest_free_sdram_block == 0xFF0000 | (x << 8) | y
                   for (x, y), info in iteritems(system_info))
        assert all(info.largest_free_sram_block == (x << 8) | y
                   for (x, y), info in iteritems(system_info))

    def test_get_machine(self):
        cn = MachineController("localhost")

        cn.get_system_info = mock.Mock(return_value=SystemInfo(1, 2, {}))

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            m = cn.get_machine(1, 2)

            # Should be flagged as deprecated
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

        # Basic sanity check
        cn.get_system_info.assert_called_once_with(1, 2)
        assert m.width == 1
        assert m.height == 2

    @pytest.mark.parametrize("app_id", [66, 12])
    def test_application_wrapper(self, app_id):
        # Create the controller
        cn = MachineController("localhost")
        cn.send_signal = mock.Mock()
        cn.sdram_alloc = mock.Mock()
        cn.sdram_alloc.return_value = 0

        # Open the context, the command run within this context should use
        # app_id=app_id
        with cn.application(app_id):
            cn.sdram_alloc_as_filelike(128, tag=0, x=0, y=0)
            cn.sdram_alloc.assert_called_once_with(128, 0, 0, 0, app_id, False)

        # Exiting the context should result in calling app_stop
        cn.send_signal.assert_called_once_with("stop")


class TestSystemInfo(object):
    """Test the SystemInfo container's utility functions."""

    def test_init(self):
        si = SystemInfo(2, 3, {})
        assert isinstance(si, dict)
        assert si.width == 2
        assert si.height == 3

    @pytest.fixture()
    def example_si(self):
        """An example SystemInfo.

        * 5x10
        * num_cores = x + 1
        * All cores are idle
        * Only north links work
        * Chip (1, 2) is dead
        * Link (1, 1, Links.north) is dead
        * Core (2, 2, 1) is rte'd
        """
        return SystemInfo(5, 10, {
            (x, y): ChipInfo(
                num_cores=x + 1,
                core_states=[consts.AppState.idle
                             if (x, y, p) != (2, 2, 1) else
                             consts.AppState.runtime_exception
                             for p in range(x + 1)],
                working_links=set([Links.north] if (x, y) != (1, 1) else []),
                largest_free_sdram_block=100,
                largest_free_sram_block=10)
            for x in range(5)
            for y in range(10)
            if (x, y) != (1, 2)
        })

    def test_iter_chips(self, example_si):
        expected = set(
            (x, y)
            for x in range(5)
            for y in range(10)
            if (x, y) != (1, 2)
        )
        assert set(example_si) == expected
        assert set(example_si.chips()) == expected

    def test_iter_dead_chips(self, example_si):
        expected = set([(1, 2)])
        assert set(example_si.dead_chips()) == expected

    def test_iter_links(self, example_si):
        expected = set(
            (x, y, Links.north)
            for x in range(5)
            for y in range(10)
            if (x, y) not in [(1, 2), (1, 1)]
        )
        assert set(example_si.links()) == expected

    def test_iter_dead_links(self, example_si):
        expected = set(
            (x, y, link)
            for x in range(5)
            for y in range(10)
            for link in Links
            if (x, y) != (1, 2) and link != Links.north
        )
        expected.add((1, 1, Links.north))
        assert set(example_si.dead_links()) == expected

    def test_iter_cores(self, example_si):
        expected_cores = set()
        for x, y in example_si.chips():
            expected_cores.update((x, y, p) for p in range(x + 1))

        for x, y, p, state in example_si.cores():
            assert (x, y, p) in expected_cores
            expected_cores.remove((x, y, p))
            if (x, y, p) != (2, 2, 1):
                assert state == consts.AppState.idle
            else:
                assert state == consts.AppState.runtime_exception

        assert len(expected_cores) == 0

    def test_contains(self, example_si):
        # Not in range or not alive
        for x, y in [(-1, 0), (0, -1), (5, 0), (0, 10), (1, 2)]:
            assert (x, y) not in example_si

            # Links on dead chips are dead
            for l in Links:
                assert (x, y, l) not in example_si

            # Cores on dead cores are dead
            assert (x, y, -1) not in example_si
            assert (x, y, 0) not in example_si
            assert (x, y, x) not in example_si
            assert (x, y, x + 1) not in example_si

        # Working chips are present
        assert (0, 0) in example_si
        assert (4, 9) in example_si

        # Working cores are present
        assert (0, 0, -1) not in example_si
        assert (0, 0, 0) in example_si
        assert (0, 0, 1) not in example_si

        # Working cores are in the correct states
        assert (0, 0, -1, consts.AppState.idle) not in example_si
        assert (0, 0, 0, consts.AppState.idle) in example_si
        assert (0, 0, 0, consts.AppState.run) not in example_si
        assert (0, 0, 1, consts.AppState.idle) not in example_si

        assert (2, 2, 1, consts.AppState.idle) not in example_si
        assert (2, 2, 1, consts.AppState.runtime_exception) in example_si

        # Working links are present
        for l in Links:
            if l is Links.north:
                assert (0, 0, l) in example_si
            else:
                assert (0, 0, l) not in example_si

        # Working chips with all dead links...
        for l in Links:
            assert (1, 1, l) not in example_si

        # Finally, an invalid tuple...
        with pytest.raises(ValueError):
            (0, ) in example_si


class TestMemoryIO(object):
    """Test the SDRAM file-like object."""
    @pytest.mark.parametrize("x, y", [(1, 3), (3, 0)])
    @pytest.mark.parametrize("start_address", [0x60000000, 0x61000000])
    @pytest.mark.parametrize("lengths", [[100, 200], [100], [300, 128, 32]])
    def test_read(self, mock_controller, x, y, start_address, lengths):
        sdram_file = MemoryIO(mock_controller, x, y,
                              start_address, start_address+500)
        assert sdram_file.tell() == 0

        # Perform the reads, check that the address is progressed
        calls = []
        offset = 0
        for n_bytes in lengths:
            sdram_file.read(n_bytes)
            assert sdram_file.tell() == offset + n_bytes
            assert sdram_file.address == start_address + offset + n_bytes
            calls.append(mock.call(start_address + offset, n_bytes, x, y, 0))
            offset = offset + n_bytes

        # Check the reads caused the appropriate calls to the machine
        # controller.
        mock_controller.read.assert_has_calls(calls)

    @pytest.mark.parametrize("x, y", [(1, 3), (3, 0)])
    @pytest.mark.parametrize("start_address, length, offset",
                             [(0x60000000, 100, 25), (0x61000000, 4, 0)])
    def test_read_no_parameter(self, mock_controller, x, y, start_address,
                               length, offset):
        sdram_file = MemoryIO(mock_controller, x, y,
                              start_address, start_address+length)

        # Assert that reading with no parameter reads the full number of bytes
        sdram_file.seek(offset)
        sdram_file.read()
        mock_controller.read.assert_called_once_with(
            start_address + offset, length - offset, x, y, 0)

    def test_read_beyond(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address=0, end_address=10)
        sdram_file.read(100)
        mock_controller.read.assert_called_with(0, 10, 0, 0, 0)

        assert sdram_file.read(1) == b''
        assert mock_controller.read.call_count == 1

    @pytest.mark.parametrize("x, y", [(4, 2), (255, 1)])
    @pytest.mark.parametrize("start_address", [0x60000004, 0x61000003])
    @pytest.mark.parametrize("lengths", [[1, 2], [1], [3, 2, 4]])
    def test_write(self, mock_controller, x, y, start_address, lengths):
        sdram_file = MemoryIO(mock_controller, x, y,
                              start_address, start_address+500)
        assert sdram_file.tell() == 0
        assert sdram_file.buffer_size == 0

        # Perform the reads, check that the address is progressed
        calls = []
        offset = 0
        for i, n_bytes in enumerate(lengths):
            chars = bytes(bytearray([i] * n_bytes))
            n_written = sdram_file.write(chars)

            assert n_written == n_bytes
            assert sdram_file.tell() == offset + n_bytes
            assert sdram_file.address == start_address + offset + n_bytes

            calls.append(mock.call(start_address + offset,
                                   chars, x, y, 0))
            offset = offset + n_bytes

        # Check the reads caused the appropriate calls to the machine
        # controller.
        mock_controller.write.assert_has_calls(calls)

    def test_write_beyond(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address=0, end_address=10)

        assert sdram_file.write(b"\x00\x00" * 12) == 10

        assert sdram_file.write(b"\x00") == 0
        sdram_file.flush()

        assert mock_controller.write.call_count == 1

    def test_close(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address=0, end_address=10)

        # Assert that after closing a file pointer it will not do anything
        assert not sdram_file.closed
        sdram_file.close()
        assert sdram_file.closed
        sdram_file.close()  # This shouldn't do anything

        # Nothing else should work
        with pytest.raises(OSError):
            sdram_file.flush()

        with pytest.raises(OSError):
            sdram_file.tell()

        with pytest.raises(OSError):
            sdram_file.seek(0)

        with pytest.raises(OSError):
            sdram_file.read(1)

        with pytest.raises(OSError):
            sdram_file.write(b'\x00')

        with pytest.raises(OSError):
            sdram_file.address

    @pytest.mark.parametrize("start_address", [0x60000004, 0x61000003])
    @pytest.mark.parametrize("seeks", [(100, -3, 32, 5, -7)])
    def test_seek_from_start(self, mock_controller, seeks, start_address):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address, start_address+200)
        assert sdram_file.tell() == 0

        for seek in seeks:
            sdram_file.seek(seek)
            assert sdram_file.tell() == seek

    @pytest.mark.parametrize("start_address", [0x60000004, 0x61000003])
    @pytest.mark.parametrize("seeks", [(100, -3, 32, 5, -7)])
    def test_seek_from_current(self, mock_controller, seeks, start_address):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address, start_address+200)
        assert sdram_file.tell() == 0

        cseek = 0
        for seek in seeks:
            sdram_file.seek(seek, from_what=1)
            assert sdram_file.tell() == cseek + seek
            cseek += seek

    @pytest.mark.parametrize("start_address, length", [(0x60000004, 300),
                                                       (0x61000003, 250)])
    @pytest.mark.parametrize("seeks", [(100, -3, 32, 5, -7)])
    def test_seek_from_end(self, mock_controller, seeks, start_address,
                           length):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address, start_address+length)
        assert sdram_file.tell() == 0

        for seek in seeks:
            sdram_file.seek(seek, from_what=2)
            assert sdram_file.tell() == length - seek

    def test_seek_from_invalid(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              0, 8)
        assert sdram_file.tell() == 0

        with pytest.raises(ValueError):
            sdram_file.seek(1, from_what=3)

    def test_slice_new_file_like(self, mock_controller):
        """Test getting a new file-like by slicing an existing one."""
        sdram_file = MemoryIO(mock_controller, 1, 4, 0x0000, 0x1000)

        # Perform a slice
        new_file = sdram_file[:100]
        assert isinstance(new_file, MemoryIO)
        assert new_file._machine_controller is mock_controller
        assert new_file._x == sdram_file._x
        assert new_file._y == sdram_file._y
        assert new_file._start_address == 0
        assert new_file._end_address == 100
        assert len(new_file) == 100

        # Perform a slice using part slices
        new_file = sdram_file[500:]
        assert isinstance(new_file, MemoryIO)
        assert new_file._machine_controller is mock_controller
        assert new_file._x == sdram_file._x
        assert new_file._y == sdram_file._y
        assert new_file._start_address == 500
        assert new_file._end_address == sdram_file._end_address
        assert len(new_file) == 0x1000 - 500

        # Perform a slice using negative slices
        new_file = sdram_file[-100:-25]
        assert isinstance(new_file, MemoryIO)
        assert new_file._machine_controller is mock_controller
        assert new_file._x == sdram_file._x
        assert new_file._y == sdram_file._y
        assert new_file._start_address == sdram_file._end_address - 100
        assert new_file._end_address == sdram_file._end_address - 25
        assert len(new_file) == 75

    @pytest.mark.parametrize("start, stop", [(-11, None), (0, 11)])
    def test_slice_saturates_new_file_like(self, mock_controller, start, stop):
        sdram_file = MemoryIO(mock_controller, 1, 4, 0, 10)

        # Perform a slice which extends beyond the end of the file
        new_file = sdram_file[start:stop]
        assert isinstance(new_file, MemoryIO)
        assert new_file._machine_controller is mock_controller
        assert new_file._x == sdram_file._x
        assert new_file._y == sdram_file._y
        assert new_file._start_address == sdram_file._start_address
        assert new_file._end_address == sdram_file._end_address

    def test_invalid_slices(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 1, 4, 0, 10)

        with pytest.raises(ValueError):
            sdram_file[0:1, 1:2]

        with pytest.raises(ValueError):
            sdram_file[10:0:-1]

        with pytest.raises(ValueError):
            sdram_file[0]

    def test_zero_length_filelike(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 0, 0, 0x100, 0x99)

        # Length should be reported as zero
        assert len(sdram_file) == 0

        # No reads should occur
        assert sdram_file.read() == b''
        assert not mock_controller.read.called

        # No writes should occur
        assert sdram_file.write(b"Hello, world!") == 0
        assert not mock_controller.write.called

        # Slicing should achieve the same thing
        new_file = sdram_file[100:-100]
        assert len(new_file) == 0

        # Now test creating an empty file from a non-empty one
        sdram_file = MemoryIO(mock_controller, 0, 0, 100, 110)
        new_file = sdram_file[5:-7]
        assert len(new_file) == 0
        assert new_file._start_address == 105
        assert new_file._end_address == 105

        # Now test creating an empty file from a non-empty one
        sdram_file = MemoryIO(mock_controller, 0, 0, 100, 110)
        new_file = sdram_file[100:]
        assert len(new_file) == 0
        assert new_file._start_address == 110
        assert new_file._end_address == 110

    @pytest.mark.parametrize(
        "get_node",
        [lambda w, x, y, z: w,
         lambda w, x, y, z: x,
         lambda w, x, y, z: y,
         lambda w, x, y, z: z,
         ]
    )
    @pytest.mark.parametrize(
        "flush_event",
        [lambda filelike: filelike.flush(),
         lambda filelike: filelike.read(1),
         lambda filelike: filelike.close()]
    )
    def test_coalescing_writes(self, get_node, flush_event):
        """Tests that writes from multiple slices of the same file-like view of
        memory are buffered until some event occurs which flushes the buffer.
        """
        # Set up
        cn = mock.Mock(spec_set=MachineController)
        parent = MemoryIO(cn, 5, 6, 0, 8, buffer_size=8)
        child_0 = parent[:4]
        child_00 = child_0[2:]
        child_1 = parent[4:]

        # Writes to child 0 followed by writes to child 1 should NOT result in
        # any writes
        child_00.write(b'\x10\x20')
        child_1.write(b'\x30\x40')
        assert not cn.write.called  # No write should have occurred

        # Performing the flush event on one of the children OR the parent
        flush_event(get_node(parent, child_0, child_00, child_1))

        # The write should have been performed
        cn.write.assert_called_once_with(2, b'\x10\x20\x30\x40', 5, 6, 0)

    def test_coalescing_writes_flushes_on_non_coalesced_write(self):
        """Tests that writes from multiple slices of the same file-like view of
        memory are buffered until a non-contiguous write occurs.
        """
        # Set up
        cn = mock.Mock(spec_set=MachineController)
        parent = MemoryIO(cn, 9, 2, 0, 8, buffer_size=8)

        with parent:
            child_0 = parent[:4]
            child_1 = parent[4:]

            child_0.write(b'\x12')  # Does not meet child 1
            child_1.write(b'\x30\x40')

        # The writes should have been performed
        cn.write.assert_has_calls([
            mock.call(0, b'\x12', 9, 2, 0),
            mock.call(4, b'\x30\x40', 9, 2, 0),
        ])

    def test_coalescing_writes_flushes_on_non_coalesced_write_2(self):
        """Tests that writes from multiple slices of the same file-like view of
        memory are buffered until a non-contiguous write occurs.
        """
        # Set up
        cn = mock.Mock(spec_set=MachineController)
        parent = MemoryIO(cn, 9, 2, 0, 8, buffer_size=8)

        with parent:
            child_0 = parent[:4]
            child_1 = parent[4:]

            child_1.write(b'\x30\x40')
            child_0.write(b'\x12')  # Does not meet child 1

        # The writes should have been performed
        cn.write.assert_has_calls([
            mock.call(4, b'\x30\x40', 9, 2, 0),
            mock.call(0, b'\x12', 9, 2, 0),
        ])

    def test_buffer_overflows(self):
        """Tests that writes from multiple slices of the same file-like view of
        memory are buffered until a non-contiguous write occurs.
        """
        # Set up
        cn = mock.Mock(spec_set=MachineController)
        parent = MemoryIO(cn, 9, 2, 0, 8, buffer_size=3)

        with parent:
            child_0 = parent[:4]
            child_1 = parent[4:]

            child_0.seek(2)
            child_0.write(b'AB')
            child_1.write(b'CD')

        # The writes should have been performed
        cn.write.assert_has_calls([
            mock.call(2, b'ABC', 9, 2, 0),
            mock.call(5, b'D', 9, 2, 0),
        ])

    def test_completely_non_coalesced(self):
        """Tests that writes from multiple slices of the same file-like view of
        memory are buffered until a non-contiguous write occurs.
        """
        # Set up
        cn = mock.Mock(spec_set=MachineController)
        parent = MemoryIO(cn, 9, 2, 0, 8, buffer_size=2)

        with parent:
            child_0 = parent[:4]
            child_1 = parent[4:]

            child_0.write(b'AB')
            child_1.write(b'CD')

        # The writes should have been performed
        cn.write.assert_has_calls([
            mock.call(0, b'AB', 9, 2, 0),
            mock.call(4, b'CD', 9, 2, 0),
        ])

    def test_coalescing_writes_overwrites(self):
        """Test that multiple writes to the same area of memory are buffered
        until flushed.
        """
        # Set up
        cn = mock.Mock(spec_set=MachineController)
        parent = MemoryIO(cn, 9, 2, 0, 8, buffer_size=8)

        # None of these writes should flush the buffer
        for start, data in [(0, b'\x44'*8), (2, b'\x22'), (7, b'\x00')]:
            parent.seek(start)
            assert not cn.write.called
            parent.write(data)
            assert not cn.write.called

        # The write should have been performed
        parent.flush()
        cn.write.assert_called_once_with(
            0, b'\x44\x44\x22\x44\x44\x44\x44\x00', 9, 2, 0
        )


@pytest.mark.parametrize(
    "entry, unpacked",
    [(b"\x00\x00\x42\x03\x01\x00\x00\x00\x55\x55\xff\xff\xff\xff\xff\xff",
      (RoutingTableEntry({Routes.east}, 0xffff5555, 0xffffffff), 66, 3)),
     (b"\x00\x00\x02\x03\x03\x00\x00\x00\x50\x55\xff\xff\xf0\xff\xff\xff",
      (RoutingTableEntry({Routes.east, Routes.north_east},
                         0xffff5550, 0xfffffff0), 2, 3)),
     (b"\x00\x00\x03\x02\x03\x00\x00\xff\x50\x55\xff\xff\xf0\xff\xff\xff",
      None),
     ]
)
def test_unpack_routing_table_entry(entry, unpacked):
    assert unpack_routing_table_entry(entry) == unpacked
