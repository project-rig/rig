import mock
import pkg_resources
import pytest
import six
from six import iteritems, itervalues
import struct
import tempfile
import os
import time
from .test_scp_connection import SendReceive, mock_conn  # noqa

from ..consts import DataType, SCPCommands, LEDAction, NNCommands, NNConstants
from ..machine_controller import (
    MachineController, SpiNNakerMemoryError, MemoryIO, SpiNNakerRouterError,
    SpiNNakerLoadingError, CoreInfo, ProcessorStatus,
    unpack_routing_table_entry
)
from ..packets import SCPPacket
from .. import regions, consts, struct_file

from rig.machine import Cores, SDRAM, SRAM, Links, Machine

from rig.routing_table import RoutingTableEntry, Routes


@pytest.fixture(scope="module")
def controller(spinnaker_ip):
    return MachineController(spinnaker_ip)


@pytest.fixture(scope="module")
def live_machine(controller):
    return controller.get_machine()


@pytest.fixture
def cn():
    cn = MachineController("localhost")
    cn._scp_data_length = 256
    return cn


@pytest.fixture
def controller_rw_mock():
    """Create a controller with mock _read and _write methods."""
    cn = MachineController("localhost")
    cn._read = mock.Mock(spec_set=[])
    cn._write = mock.Mock(spec_set=[])
    cn._scp_data_length = 256

    def read_mock(x, y, p, address, length_bytes, data_type=DataType.byte):
        return b'\x00' * length_bytes

    cn._read.side_effect = read_mock

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
    # Assuming a 4-node board! Change this as required.
    # Boot the board
    controller.boot(width=spinnaker_width, height=spinnaker_height)

    # Assert that the board is booted, messy!
    sver = controller.get_software_version(0, 0, 0)
    assert sver.version >= 1.3


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

    def test_set_get_clear_iptag(self, controller):
        # Get our address, then add a new IPTag pointing
        # **YUCK**
        ip_addr = controller.connections[0].sock.getsockname()[0]
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
            targets
        )

        # Read back a word to test that the application loaded
        for (t_x, t_y), cores in iteritems(targets):
            with controller(x=t_x, y=t_y):
                print(t_x, t_y)
                addr_base = controller.read_struct_field("sv", "sdram_base")

                for t_p in cores:
                    addr = addr_base + 4 * t_p
                    data = struct.unpack(
                        "<I", controller.read(addr, 4, t_x, t_y)
                    )[0]
                    print(hex(data))
                    x = (data & 0xff000000) >> 24
                    y = (data & 0x00ff0000) >> 16
                    p = (data & 0x0000ffff)
                    assert p == t_p and x == t_x and y == t_y

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

    def test_get_machine(self, live_machine, spinnaker_width,
                         spinnaker_height):
        # Just check that the output of get_machine is sane, doesn't verify
        # that it is actually correct. This test will fail if the target
        # machine is very dead...
        m = live_machine

        # This test will fail if the system has dead chips on its periphery
        assert m.width == spinnaker_width
        assert m.height == spinnaker_height

        # Check that *most* chips aren't dead or have resource exceptions
        assert len(m.chip_resource_exceptions) < (m.width * m.height) / 2
        assert len(m.dead_chips) < (m.width * m.height) / 2
        assert len(m.dead_links) < (m.width * m.height * 6) / 2

        # Check that those chips which are reported as dead are within the
        # bounds of the system
        for (x, y) in m.chip_resource_exceptions:
            assert 0 <= x < m.width
            assert 0 <= y < m.height
        for (x, y) in m.dead_chips:
            assert 0 <= x < m.width
            assert 0 <= y < m.height
            assert (x, y) not in m.chip_resource_exceptions
        for x, y, link in m.dead_links:
            assert 0 <= x < m.width
            assert 0 <= y < m.height
            assert (x, y) not in m.chip_resource_exceptions
            assert link in Links

    def test_get_machine_spinn_5(self, live_machine, spinnaker_width,
                                 spinnaker_height, is_spinn_5_board):
        # Verify get_machine in the special case when the attached machine is a
        # single SpiNN-5 or SpiNN-4 board. Verifies sanity of returned values.
        m = live_machine
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
        nominal_dead_chips = set((x, y)
                                 for x in range(m.width)
                                 for y in range(m.height)) - nominal_live_chips

        # Check that all chips not part of a SpiNN-5 board are found to be dead
        assert nominal_dead_chips.issubset(m.dead_chips)

        # Check all links to chips out of the board are found to be dead
        for link, (dx, dy) in ((Links.north, (+0, +1)),
                               (Links.west, (-1, +0)),
                               (Links.south_west, (-1, -1)),
                               (Links.south, (+0, -1)),
                               (Links.east, (+1, +0)),
                               (Links.north_east, (+1, +1))):
            for (x, y) in nominal_live_chips:
                neighbour = ((x + dx), (y + dy))
                if neighbour not in nominal_live_chips:
                    assert (x, y, link) in m.dead_links

    @pytest.mark.parametrize("data", [b"Hello, SpiNNaker",
                                      b"Bonjour SpiNNaker"])
    def test_sdram_alloc_as_filelike_read_write(self, controller, data):
        # Allocate some memory, write to it and check that we can read back
        with controller(x=1, y=0):
            mem = controller.sdram_alloc_as_filelike(len(data))
            assert mem.write(data) == len(data)
            mem.seek(0)
            assert mem.read(len(data)) == data

    @pytest.mark.order_id("live_test_load_routes")
    @pytest.mark.order_after("live_test_load_application")
    @pytest.mark.parametrize(
        "routes",
        [([RoutingTableEntry({Routes.east}, 0x0000ffff, 0xffffffff),
           RoutingTableEntry({Routes.west}, 0xffff0000, 0xffff0000)])
         ]
    )
    def test_load_and_retrieve_routing_tables(self, controller, routes):
        with controller(x=1, y=1):
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
        with controller(x=1, y=1):
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

    @pytest.mark.parametrize("size", [128, 256])
    def test_scp_data_length(self, size):
        cn = MachineController("localhost")
        cn._scp_data_length = None
        cn.get_software_version = mock.Mock()
        cn.get_software_version.return_value = CoreInfo(
            None, None, None, None, size, None, None)

        assert cn.scp_data_length == size
        cn.get_software_version.assert_called_once_with(0, 0)

    @pytest.mark.parametrize(  # noqa
        "address, data, dtype",
        [(0x60000000, b"Hello, World", DataType.byte),
         (0x60000002, b"Hello, World", DataType.short),
         (0x60000004, b"Hello, World", DataType.word)])
    def test__write(self, mock_conn, address, data, dtype):
        """Check writing data can be performed correctly.

        SCP Layout
        ----------
        Outgoing:
            cmd_rc : 3
            arg_1 : address to write to
            arg_2 : number of bytes to write
            arg_3 : Type of data to write:
                        - 0 : byte
                        - 1 : short
                        - 2 : word
                    This only affects the speed of the operation on SpiNNaker.

        Return:
            cmd_rc : 0x80 -- success
        """
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        # Try the write
        cn._write(0, 1, 2, address, data, dtype)

        # Assert that there was 1 packet sent and that it was sane
        call = cn._send_scp.call_args[0]
        assert call == (0, 1, 2, SCPCommands.write, address, len(data),
                        int(dtype), data)

    @pytest.mark.parametrize(
        "start_address,data,data_type",
        [(0x60000000, b'\x00', DataType.byte),
         (0x60000001, b'\x00', DataType.byte),
         (0x60000001, b'\x00\x00', DataType.byte),
         (0x60000001, b'\x00\x00\x00\x00', DataType.byte),
         (0x60000000, b'\x00\x00', DataType.short),
         (0x60000002, b'\x00\x00\x00\x00', DataType.short),
         (0x60000004, b'\x00\x00\x00\x00', DataType.word),
         (0x60000001, 512*b'\x00\x00\x00\x00', DataType.byte),
         (0x60000002, 512*b'\x00\x00\x00\x00', DataType.short),
         (0x60000000, 512*b'\x00\x00\x00\x00', DataType.word),
         ])
    def test_write(self, controller_rw_mock, start_address, data, data_type):
        # Write the data
        controller_rw_mock.write(start_address, data, x=0, y=1, p=2)

        # Check that the correct calls to write were made
        segments = []
        address = start_address
        addresses = []
        while len(data) > 0:
            addresses.append(address)
            segments.append(data[0:controller_rw_mock._scp_data_length])

            data = data[controller_rw_mock._scp_data_length:]
            address += len(segments[-1])

        controller_rw_mock._write.assert_has_calls(
            [mock.call(0, 1, 2, a, d, data_type) for (a, d) in
             zip(addresses, segments)]
        )

    @pytest.mark.parametrize(
        "address, data, dtype",
        [(0x60000000, b"Hello, World", DataType.byte),
         (0x60000002, b"Hello, World", DataType.short),
         (0x60000004, b"Hello, World", DataType.word)])
    def test__read(self, address, data, dtype):
        """Check reading data can be performed correctly.

        SCP Layout
        ----------
        Outgoing:
            cmd_rc : 2
            arg_1 : address to read from
            arg_2 : number of bytes to read
            arg_3 : Type of data to read:
                        - 0 : byte
                        - 1 : short
                        - 2 : word
                    This only affects the speed of the operation on SpiNNaker.

        Return:
            cmd_rc : 0x80 -- success
            data : data read from memory
        """
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = mock.Mock(spec_set=SCPPacket)
        cn._send_scp.return_value.data = data

        # Try the read
        read = cn._read(0, 1, 2, address, len(data), dtype)

        # Assert that there was 1 packet sent and that it was sane
        assert cn._send_scp.call_count == 1
        call = cn._send_scp.call_args[0]
        assert call == (0, 1, 2, SCPCommands.read, address, len(data),
                        int(dtype))
        assert read == data

    @pytest.mark.parametrize(
        "n_bytes, data_type, start_address, n_packets",
        [(1, DataType.byte, 0x60000000, 1),   # Only reading a byte
         (3, DataType.byte, 0x60000000, 1),   # Can only read bytes
         (2, DataType.byte, 0x60000001, 1),   # Offset from short
         (4, DataType.byte, 0x60000001, 1),   # Offset from word
         (2, DataType.short, 0x60000002, 1),  # Reading a short
         (6, DataType.short, 0x60000002, 1),  # Can read shorts
         (4, DataType.short, 0x60000002, 1),  # Offset from word
         (4, DataType.word, 0x60000004, 1),   # Reading a word
         (257, DataType.byte, 0x60000001, 2),
         (511, DataType.byte, 0x60000001, 2),
         (258, DataType.byte, 0x60000001, 2),
         (256, DataType.byte, 0x60000001, 1),
         (258, DataType.short, 0x60000002, 2),
         (514, DataType.short, 0x60000002, 3),
         (516, DataType.short, 0x60000002, 3),
         (256, DataType.word, 0x60000004, 1)
         ])
    def test_read(self, controller_rw_mock, n_bytes, data_type, start_address,
                  n_packets):
        # Read an amount of memory specified by the size.
        data = controller_rw_mock.read(start_address, n_bytes, x=0, y=0, p=0)
        assert len(data) == n_bytes

        # Assert that n calls were made to the communicator with the correct
        # parameters.
        offset = start_address
        offsets = []
        lens = []
        while n_bytes > 0:
            offsets += [offset]
            lens += [min((controller_rw_mock._scp_data_length, n_bytes))]
            offset += lens[-1]
            n_bytes -= controller_rw_mock._scp_data_length

        assert len(lens) == len(offsets) == n_packets, "Test is broken"

        controller_rw_mock._read.assert_has_calls(
            [mock.call(0, 0, 0, o, l, data_type) for (o, l) in
             zip(offsets, lens)]
        )

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

    @pytest.mark.parametrize("app_id", [30, 33])
    @pytest.mark.parametrize("size", [8, 200])
    @pytest.mark.parametrize("tag", [0, 2])
    @pytest.mark.parametrize("addr", [0x67000000, 0x61000000])
    def test_sdram_alloc_success(self, app_id, size, tag, addr):
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

        # Try the allocation
        address = cn.sdram_alloc(size, tag, 1, 2, app_id=app_id)

        # Check the return value
        assert address == addr

        # Check the packet was sent as expected
        cn._send_scp.assert_called_once_with(1, 2, 0, 28, app_id << 8,
                                             size, tag)

    @pytest.mark.parametrize("x, y", [(1, 3), (5, 6)])
    @pytest.mark.parametrize("size", [8, 200])
    def test_sdram_alloc_fail(self, x, y, size):
        """Test that sdram_alloc raises an exception when ALLOC fails."""
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                              0x80, 0, 0, None, None, b"")

        with pytest.raises(SpiNNakerMemoryError) as excinfo:
            cn.sdram_alloc(size, x=x, y=y, app_id=30)

        assert str((x, y)) in str(excinfo.value)
        assert str(size) in str(excinfo.value)

    @pytest.mark.parametrize("x, y", [(0, 1), (3, 4)])
    @pytest.mark.parametrize("app_id", [30, 33])
    @pytest.mark.parametrize("size", [8, 200])
    @pytest.mark.parametrize("tag", [0, 2])
    @pytest.mark.parametrize("addr", [0x67000000, 0x61000000])
    def test_sdram_alloc_as_filelike(self, app_id, size, tag, addr, x, y):
        """Test allocing and getting a file-like object returned."""
        # Create the mock controller
        cn = MachineController("localhost")
        cn.sdram_alloc = mock.Mock(return_value=addr)

        # Try the allocation
        fp = cn.sdram_alloc_as_filelike(size, tag, x, y, app_id=app_id)

        # Check the fp has the expected start and end
        assert fp._start_address == addr
        assert fp._end_address == addr + size

        # Check the x and y are correct
        assert fp._machine_controller is cn
        assert fp._x == x
        assert fp._y == y

    @pytest.mark.parametrize("x, y, p", [(0, 1, 2), (2, 5, 6)])
    @pytest.mark.parametrize(
        "which_struct, field, expected",
        [("sv", "dbg_addr", 0),
         ("sv", "status_map", (0, )*20),
         ])
    def test_read_struct_field(self, x, y, p, which_struct, field, expected):
        # Open the struct file
        struct_data = pkg_resources.resource_string("rig", "boot/sark.struct")
        structs = struct_file.read_struct_file(struct_data)
        assert (six.b(which_struct) in structs and
                six.b(field) in structs[six.b(which_struct)]), "Test is broken"

        # Create the mock controller
        cn = MachineController("localhost")
        cn.structs = structs
        cn.read = mock.Mock()
        cn.read.return_value = b"\x00" * struct.calcsize(
            structs[six.b(which_struct)][six.b(field)].pack_chars) * \
            structs[six.b(which_struct)][six.b(field)].length

        # Perform the struct read
        with cn(x=x, y=y, p=p):
            returned = cn.read_struct_field(which_struct, field)
        assert returned == expected

        which_struct = six.b(which_struct)
        field = six.b(field)
        # Check that read was called appropriately
        assert cn.read.called_once_with(
            structs[which_struct].base + structs[which_struct][field].offset,
            struct.calcsize(structs[which_struct][field].pack_chars),
            x, y, p
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
        [(31, False, [1, 2, 3]), (12, True, [5])]
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
        assert cn._send_scp.call_count == n_blocks + 2
        # Flood-fill start
        (x, y, p, cmd, arg1, arg2, arg3) = cn._send_scp.call_args_list[0][0]
        assert x == y == p == 0
        assert cmd == SCPCommands.nearest_neighbour_packet
        op = (arg1 & 0xff000000) >> 24
        assert op == NNCommands.flood_fill_start
        blocks = (arg1 & 0x0000ff00) >> 8
        assert blocks == n_blocks

        assert arg2 == regions.get_region_for_chip(0, 1, level=3)

        assert arg3 & 0x80000000  # Assert that we allocate ID on SpiNNaker
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
                cn._send_scp.call_args_list[n+1][0]

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
        print(hex(NNCommands.flood_fill_end << 24))
        assert arg1 & 0xff000000 == NNCommands.flood_fill_end << 24
        assert arg2 & 0xff000000 == app_id << 24
        assert arg2 & 0x0003ffff == coremask

        exp_flags = 0x00000000
        if wait:
            exp_flags |= consts.AppFlags.wait
        assert arg2 & 0x00fc0000 == exp_flags << 18

    def test_load_and_check_aplxs(self):
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
            cn.load_application("test.aplx", targets, wait=True)

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
            cn.load_application({"test.aplx": targets})

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
                cn.load_application({"test.aplx": targets})

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
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.return_value = sum(1 << l for l in links)

        assert cn.get_working_links(x=0, y=0) == links

        assert cn.read_struct_field.called_once_with("sv", "link_up", 0, 0, 0)

    @pytest.mark.parametrize("num_cpus", [1, 18])
    def test_get_num_working_cores(self, num_cpus):
        cn = MachineController("localhost")
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.return_value = num_cpus

        assert cn.get_num_working_cores(x=0, y=0) == num_cpus
        assert cn.read_struct_field.called_once_with("sv", "num_cpus", 0, 0, 0)

    def test_get_machine(self):
        cn = MachineController("localhost")

        # Return sensible values for heap sizes (taken from manual)
        sdram_heap = 0x60640000
        sdram_sys = 0x67800000
        sysram_heap = 0xE5001100
        vcpu_base = 0xE5007000

        def read_struct_field(struct_name, field_name, x, y, p=0):
            return {
                ("sv", "sdram_heap"): sdram_heap,
                ("sv", "sdram_sys"): sdram_sys,
                ("sv", "sysram_heap"): sysram_heap,
                ("sv", "vcpu_base"): vcpu_base,
            }[(struct_name, field_name)]
        cn.read_struct_field = mock.Mock()
        cn.read_struct_field.side_effect = read_struct_field

        # Return a set of p2p tables where an 8x8 set of chips is alive with
        # all chips with (3,3) being dead.
        cn.get_p2p_routing_table = mock.Mock()
        cn.get_p2p_routing_table.return_value = {
            (x, y): (consts.P2PTableEntry.north
                     if x < 8 and y < 8 and (x, y) != (3, 3) else
                     consts.P2PTableEntry.none)
            for x in range(256)
            for y in range(256)
        }

        # Return 18 working cores except for (2, 2) which will have only 3
        # cores.

        def get_num_working_cores(x, y):
            return 18 if (x, y) != (2, 2) else 3
        cn.get_num_working_cores = mock.Mock()
        cn.get_num_working_cores.side_effect = get_num_working_cores

        # Return all working links except for (4, 4) which will have no north
        # link.

        def get_working_links(x, y):
            if (x, y) != (4, 4):
                return set(Links)
            else:
                return set(Links) - set([Links.north])
        cn.get_working_links = mock.Mock()
        cn.get_working_links.side_effect = get_working_links

        m = cn.get_machine()

        # Check that the machine is correct
        assert isinstance(m, Machine)
        assert m.width == 8
        assert m.height == 8
        assert m.chip_resources == {
            Cores: 18,
            SDRAM: sdram_sys - sdram_heap,
            SRAM: vcpu_base - sysram_heap,
        }
        assert m.chip_resource_exceptions == {
            (2, 2): {
                Cores: 3,
                SDRAM: sdram_sys - sdram_heap,
                SRAM: vcpu_base - sysram_heap,
            },
        }
        assert m.dead_chips == set([(3, 3)])
        assert m.dead_links == set([(4, 4, Links.north)])

        # Check that only the expected calls were made to mocks
        cn.read_struct_field.assert_has_calls([
            mock.call("sv", "sdram_heap", 0, 0),
            mock.call("sv", "sdram_sys", 0, 0),
            mock.call("sv", "sysram_heap", 0, 0),
            mock.call("sv", "vcpu_base", 0, 0),
        ], any_order=True)
        cn.get_p2p_routing_table.assert_called_once_with(0, 0)
        cn.get_num_working_cores.assert_has_calls([
            mock.call(x, y) for x in range(8) for y in range(8)
            if (x, y) != (3, 3)
        ], any_order=True)
        cn.get_working_links.assert_has_calls([
            mock.call(x, y) for x in range(8) for y in range(8)
            if (x, y) != (3, 3)
        ], any_order=True)

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
            cn.sdram_alloc.assert_called_once_with(128, 0, 0, 0, app_id)

        # Exiting the context should result in calling app_stop
        cn.send_signal.assert_called_once_with("stop")


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
        mock_controller.read.assert_called_one_with(
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
    @pytest.mark.parametrize("lengths", [[100, 200], [100], [300, 128, 32]])
    def test_write(self, mock_controller, x, y, start_address, lengths):
        sdram_file = MemoryIO(mock_controller, x, y,
                              start_address, start_address+500)
        assert sdram_file.tell() == 0

        # Perform the reads, check that the address is progressed
        calls = []
        offset = 0
        for i, n_bytes in enumerate(lengths):
            n_written = sdram_file.write(chr(i % 256) * n_bytes)
            assert n_written == n_bytes
            assert sdram_file.tell() == offset + n_bytes
            assert sdram_file.address == start_address + offset + n_bytes
            calls.append(mock.call(start_address + offset,
                                   chr(i % 256) * n_bytes, x, y, 0))
            offset = offset + n_bytes

        # Check the reads caused the appropriate calls to the machine
        # controller.
        mock_controller.write.assert_has_calls(calls)

    def test_write_beyond(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address=0, end_address=10)

        assert sdram_file.write(b"\x00\x00" * 12) == 10

        assert sdram_file.write(b"\x00") == 0
        assert mock_controller.write.call_count == 1

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
