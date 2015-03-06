import mock
import pkg_resources
import pytest
from six import iteritems
import struct
import tempfile
from .test_scp_connection import SendReceive, mock_conn  # noqa

from ..consts import DataType, SCPCommands, LEDAction, NNCommands, NNConstants
from ..machine_controller import (
    MachineController, SpiNNakerMemoryError, MemoryIO, SpiNNakerRouterError,
    SpiNNakerLoadingError
)
from ..packets import SCPPacket
from .. import regions, consts, struct_file

from rig.routing_table import RoutingTableEntry, Routes


@pytest.fixture(scope="module")
def controller(spinnaker_ip):
    return MachineController(spinnaker_ip)


@pytest.fixture
def controller_rw_mock():
    """Create a controller with mock _read and _write methods."""
    cn = MachineController("localhost")
    cn._read = mock.Mock(spec_set=[])
    cn._write = mock.Mock(spec_set=[])

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

    # Delete the file when done
    def teardown():
        aplx_file.delete = True
        aplx_file.close()

    return aplx_file.name


def rc_ok(last):
    """Returns an RC ok packet."""
    packet = SCPPacket.from_bytestring(last)
    packet.cmd_rc = 0x80
    packet.arg1 = packet.arg2 = packet.arg3 = None
    packet.data = b""
    return packet.bytestring


@pytest.mark.incremental
class TestMachineControllerLive(object):
    """Test the machine controller against a running SpiNNaker machine."""
    @pytest.mark.no_boot  # Don't run if booting is disabled
    def test_boot(self, controller, spinnaker_width, spinnaker_height):
        """Test that the board can be booted."""
        # Assuming a 4-node board! Change this as required.
        # Boot the board
        controller.boot(width=spinnaker_width, height=spinnaker_height)

        # Assert that the board is booted, messy!
        sver = controller.get_software_version(0, 0, 0)
        assert sver.version >= 1.3

    def test_get_software_version(self, controller, spinnaker_width,
                                  spinnaker_height):
        """Test getting the software version data."""
        # (Assuming a 4-node board) Get the software version for a number of
        # cores.
        for x in range(2):
            for y in range(2):
                sver = controller.get_software_version(x=x, y=y, processor=0)
                assert sver.virt_cpu == 0
                assert b"SpiNNaker" in bytes(sver.version_string)
                assert sver.version >= 1.3

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
                controller.set_led(1, x=x, y=y, action=LEDAction.on)

    def test_led_off(self, controller):
        for x in range(2):
            for y in range(2):
                controller.set_led(1, x=x, y=y, action=LEDAction.off)

    def test_led_toggle(self, controller):
        for _ in range(2):  # Toggle On -> Toggle Off
            for x in range(2):
                for y in range(2):
                    controller.set_led(1, x=x, y=y, action=LEDAction.toggle)

    @pytest.mark.parametrize(
        "targets",
        [{(1, 1): {3, 4}, (1, 0): {5}},
         {(0, 1): {2}}]
    )
    def test_flood_fill_aplx(self, controller, targets):
        """Test loading an APLX.  The given APLX writes (x << 24) | (y << 16) |
        p into sdram_base + p*4; so we can check everything works by looking at
        that memory address.
        """
        assert isinstance(controller, MachineController)
        controller.flood_fill_aplx(
            pkg_resources.resource_filename("rig", "binaries/rig_test.aplx"),
            targets
        )

        # Read back a word to test that the application loaded
        for (t_x, t_y), cores in iteritems(targets):
            with controller(x=t_x, y=t_y):
                print(t_x, t_y)
                addr_base = controller.read_struct_field(b"sv", b"sdram_base")

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


class TestMachineController(object):
    """Test the machine controller against the ideal protocol.

        - Check that transmitted packets are sensible.
        - Check that error codes / correct returns are dealt with correctly.
    """
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
        # Build the response packet
        def build_response_packet(last):
            """Builds a packet indicating:

            p2p_address : (1, 2)
            pcpu : 3
            vcpu : 4

            version_number : 2.56
            buffer_size : 256

            build_date : 888999
            version_string : "Hello, World!"
            """
            packet = SCPPacket.from_bytestring(last)
            packet.cmd_rc = 0x80  # Respond OK
            packet.arg1 = ((1 << 8 | 2) << 16) | (3 << 8) | 4
            packet.arg2 = (256 << 16) | 256
            packet.arg3 = 888999
            packet.data = b"Hello, World!"
            return packet.bytestring

        sr = SendReceive(build_response_packet)
        mock_conn.sock.send.side_effect = sr.send
        mock_conn.sock.recv.side_effect = sr.recv

        # Create the machine controller
        cn = MachineController("localhost")
        cn._send_scp = mock_conn.send_scp

        # Run the software version command
        sver = cn.get_software_version(0, 1, 2)

        # Assert that the response is correct
        assert sver.p2p_address == (1 << 8) | 2
        assert sver.physical_cpu == 3
        assert sver.virt_cpu == 4
        assert sver.version == 2.56
        assert sver.buffer_size == 256
        assert sver.build_date == 888999
        assert sver.version_string == b"Hello, World!"

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
            segments.append(data[0:consts.SCP_DATA_LENGTH])

            data = data[consts.SCP_DATA_LENGTH:]
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
            lens += [min((consts.SCP_DATA_LENGTH, n_bytes))]
            offset += lens[-1]
            n_bytes -= consts.SCP_DATA_LENGTH

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

    @pytest.mark.parametrize("action", [LEDAction.on, LEDAction.off,
                                        LEDAction.toggle, LEDAction.toggle])
    @pytest.mark.parametrize("x", [0, 1])
    @pytest.mark.parametrize("y", [0, 1])
    @pytest.mark.parametrize("led", [0, 1])
    def test_led_controls(self, action, x, y, led):
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
        assert kwargs["arg1"] == action << (led * 2)

    @pytest.mark.parametrize("app_id", [30, 33])
    @pytest.mark.parametrize("size", [8, 200])
    @pytest.mark.parametrize("tag", [0, 2])
    @pytest.mark.parametrize("addr", [0x67000000, 0x61000000])
    def test_sdram_alloc_success(self, app_id, size, tag, addr):
        """Check allocating a region of SDRAM.

        Outgoing:
            cmd_rc : 28
            arg1 : op code (0) << 8 | app_id
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
        cn._send_scp.assert_called_once_with(1, 2, 0, 28, app_id, size, tag)

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
    def test_sdram_alloc_and_open(self, app_id, size, tag, addr, x, y):
        """Test allocing and getting a file-like object returned."""
        # Create the mock controller
        cn = MachineController("localhost")

        cn._send_scp = mock.Mock()
        cn._send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                              0x80, 0, addr, None, None, b"")

        # Try the allocation
        fp = cn.sdram_alloc_as_io(size, tag, x, y, app_id=app_id)

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
        [(b"sv", b"dbg_addr", 0),
         (b"sv", b"status_map", (0, )*20),
         (b"vcpu", b"sw_count", 0),
         ])
    def test_read_struct_field(self, x, y, p, which_struct, field, expected):
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
            returned = cn.read_struct_field(which_struct, field)
        assert returned == expected

        # Check that read was called appropriately
        assert cn.read.called_once_with(
            structs[which_struct].base + structs[which_struct][field].offset,
            struct.calcsize(structs[which_struct][field].pack_chars),
            x, y, p
        )

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
    def test_flood_fill_aplx_single_aplx(self, aplx_file, app_id, wait, cores,
                                         present_map):
        """Test loading a single APLX to a set of cores."""
        # Create the mock controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()

        # Target cores for APLX
        targets = {(0, 1): set(cores)}

        # Attempt to load
        with cn(app_id=app_id, wait=wait):
            if present_map:
                cn.flood_fill_aplx({aplx_file: targets})
            else:
                cn.flood_fill_aplx(aplx_file, targets)

        # Determine the expected core mask
        coremask = 0x00000000
        for c in cores:
            coremask |= 1 << c

        # Read the aplx_data
        with open(aplx_file, "rb") as f:
            aplx_data = f.read()

        n_blocks = ((len(aplx_data) + consts.SCP_DATA_LENGTH - 1) //
                    consts.SCP_DATA_LENGTH)

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
        address = consts.SARK_DATA_BASE
        for n in range(0, n_blocks):
            # Get the next block of data
            (block_data, aplx_data) = (aplx_data[:consts.SCP_DATA_LENGTH],
                                       aplx_data[consts.SCP_DATA_LENGTH:])

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
        cn.read_struct_field = mock.Mock()
        cn.send_signal = mock.Mock()

        # Construct a list of targets and a list of failed targets
        app_id = 27
        targets = {(0, 1): {2, 4}}
        failed_targets = {(0, 1, 4)}
        faileds = {(0, 1): {4}}

        def read_struct_field(sn, fn, x, y, p):
            if (x, y, p) in failed_targets:
                failed_targets.remove((x, y, p))  # Succeeds next time
                return consts.AppState.idle
            else:
                return consts.AppState.wait
        cn.read_struct_field.side_effect = read_struct_field

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
        cn.read_struct_field.assert_has_calls([
            mock.call(b"vcpu", b"cpu_state", x, y, p)
            for (x, y), ps in iteritems(targets) for p in ps
        ] + [
            mock.call(b"vcpu", b"cpu_state", x, y, p)
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
        cn.read_struct_field = mock.Mock()
        cn.send_signal = mock.Mock()

        # Construct a list of targets and a list of failed targets
        app_id = 27
        targets = {(0, 1): {2, 4}}
        failed_targets = {(0, 1, 4)}
        faileds = {(0, 1): {4}}

        def read_struct_field(sn, fn, x, y, p):
            if (x, y, p) in failed_targets:
                failed_targets.remove((x, y, p))  # Succeeds next time
                return consts.AppState.idle
            else:
                return consts.AppState.wait
        cn.read_struct_field.side_effect = read_struct_field

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
        cn.read_struct_field.assert_has_calls([
            mock.call(b"vcpu", b"cpu_state", x, y, p)
            for (x, y), ps in iteritems(targets) for p in ps
        ] + [
            mock.call(b"vcpu", b"cpu_state", x, y, p)
            for (x, y), ps in iteritems(faileds) for p in ps
        ])

        # Start signal sent
        cn.send_signal.assert_called_once_with(consts.AppSignal.start, app_id)

    def test_load_and_check_aplxs_fails(self):
        """Test that APLX loading takes place multiple times if one of the
        chips fails to be placed in the wait state.
        """
        # Construct the machine controller
        cn = MachineController("localhost")
        cn._send_scp = mock.Mock()
        cn.flood_fill_aplx = mock.Mock()
        cn.read_struct_field = mock.Mock()
        cn.send_signal = mock.Mock()

        # Construct a list of targets and a list of failed targets
        app_id = 27
        targets = {(0, 1): {2, 4}}
        failed_targets = {(0, 1, 4)}

        def read_struct_field(sn, fn, x, y, p):
            if (x, y, p) in failed_targets:
                return consts.AppState.idle
            else:
                return consts.AppState.wait
        cn.read_struct_field.side_effect = read_struct_field

        # Test that loading applications results in calls to flood_fill_aplx,
        # and read_struct_field and that failed cores are reloaded.
        with cn(app_id=app_id):
            with pytest.raises(SpiNNakerLoadingError) as excinfo:
                cn.load_application({"test.aplx": targets})

        assert "(0, 1, 4)" in str(excinfo.value)

    def test_send_signal_fails(self):
        """Test that we refuse to send diagnostic signals which need treating
        specially.
        """
        cn = MachineController("localhost")

        with pytest.raises(ValueError):
            cn.send_signal(consts.AppDiagnosticSignal.AND)

    @pytest.mark.parametrize("app_id", [16, 30])
    @pytest.mark.parametrize("signal", [consts.AppSignal.sync0,
                                        consts.AppSignal.timer,
                                        consts.AppSignal.start])
    def test_send_signal_one_target(self, app_id, signal):
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
        assert arg1 == consts.signal_types[signal]
        assert arg2 & 0x000000ff == app_id
        assert arg2 & 0x0000ff00 == 0xff00  # App mask for 1 app_id
        assert arg2 & 0x00ff0000 == signal << 16
        assert arg3 == 0x0000ffff  # Transmit to all

    @pytest.mark.parametrize("x, y, app_id", [(1, 2, 32), (4, 10, 17)])
    @pytest.mark.parametrize(
        "entries",
        [[RoutingTableEntry({Routes.east}, 0xffff0000, 0xffff0000),
          RoutingTableEntry({Routes.west}, 0xfffc0000, 0xfffff000)],
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

        # (2) Request for the b"sv" b"sdram_sys" value
        cn.read_struct_field.assert_called_once_with(b"sv", b"sdram_sys", x, y)

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
            for route in entries[i].route:
                exp_route |= route

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
            calls.append(mock.call(x, y, 0, start_address + offset, n_bytes))
            offset = offset + n_bytes

        # Check the reads caused the appropriate calls to the machine
        # controller.
        mock_controller.read.assert_has_calls(calls)

    def test_read_beyond(self, mock_controller):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address=0, end_address=10)
        sdram_file.read(100)
        mock_controller.read.assert_called_with(0, 0, 0, 0, 10)

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
            calls.append(mock.call(x, y, 0, start_address + offset,
                                   chr(i % 256) * n_bytes))
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
    def test_seek(self, mock_controller, seeks, start_address):
        sdram_file = MemoryIO(mock_controller, 0, 0,
                              start_address, start_address+200)
        assert sdram_file.tell() == 0

        cseek = 0
        for seek in seeks:
            sdram_file.seek(seek)
            assert sdram_file.tell() == cseek + seek
            cseek += seek
