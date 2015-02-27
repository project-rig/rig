import mock
import pytest
import struct
from .test_scp_connection import SendReceive, mock_conn  # noqa

from ..consts import DataType, SCPCommands, LEDAction
from ..machine_controller import MachineController, SpiNNakerMemoryError
from ..packets import SCPPacket


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


class TestMachineController(object):
    """Test the machine controller against the ideal protocol.

        - Check that transmitted packets are sensible.
        - Check that error codes / correct returns are dealt with correctly.
    """
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
        cn.send_scp = mock_conn.send_scp

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
        cn.send_scp = mock.Mock()

        # Try the write
        cn._write(0, 1, 2, address, data, dtype)

        # Assert that there was 1 packet sent and that it was sane
        call = cn.send_scp.call_args[0]
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
            segments.append(data[0:256])

            data = data[256:]
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
        cn.send_scp = mock.Mock()
        cn.send_scp.return_value = mock.Mock(spec_set=SCPPacket)
        cn.send_scp.return_value.data = data

        # Try the read
        read = cn._read(0, 1, 2, address, len(data), dtype)

        # Assert that there was 1 packet sent and that it was sane
        assert cn.send_scp.call_count == 1
        call = cn.send_scp.call_args[0]
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
            lens += [min((256, n_bytes))]
            offset += lens[-1]
            n_bytes -= 256

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
        cn.send_scp = mock.Mock()

        # Set the IPTag
        cn.iptag_set(iptag, addr, port, x=0, y=1)

        # Assert that there was 1 packet sent and that it was sane
        assert cn.send_scp.call_count == 1
        call = cn.send_scp.call_args[0]
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
        cn.send_scp = mock.Mock()
        cn.send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                             0x80, 0, 0, 0, 0, data)

        # Get the IPtag
        r_iptag = cn.iptag_get(iptag, x=1, y=2)

        # Assert that there was 1 packet sent and that it was sane
        assert cn.send_scp.call_count == 1
        call = cn.send_scp.call_args[0]
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
        cn.send_scp = mock.Mock()

        # Clear the IPtag
        cn.iptag_clear(iptag, x=1, y=2)

        # Assert that there was 1 packet sent and that it was sane
        assert cn.send_scp.call_count == 1
        call = cn.send_scp.call_args[0]
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
        cn.send_scp = mock.Mock()

        # Perform the action
        cn.set_led(led, x=x, y=y, action=action)

        # Assert that there was 1 packet sent and that it was sane
        assert cn.send_scp.call_count == 1
        call, kwargs = cn.send_scp.call_args
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

        cn.send_scp = mock.Mock()
        cn.send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                             0x80, 0, addr, None, None, b"")

        # Try the allocation
        address = cn.sdram_alloc(size, tag, 1, 2, app_id=app_id)

        # Check the return value
        assert address == addr

        # Check the packet was sent as expected
        cn.send_scp.assert_called_once_with(1, 2, 0, 28, app_id, size, tag)

    @pytest.mark.parametrize("x, y", [(1, 3), (5, 6)])
    @pytest.mark.parametrize("size", [8, 200])
    def test_sdram_alloc_fail(self, x, y, size):
        """Test that sdram_alloc raises an exception when ALLOC fails."""
        # Create the mock controller
        cn = MachineController("localhost")
        cn.send_scp = mock.Mock()
        cn.send_scp.return_value = SCPPacket(False, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                                             0x80, 0, 0, None, None, b"")

        with pytest.raises(SpiNNakerMemoryError) as excinfo:
            cn.sdram_alloc(size, x=x, y=y, app_id=30)

        assert str((x, y)) in str(excinfo.value)
        assert str(size) in str(excinfo.value)
