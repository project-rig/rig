import collections
import mock
import pytest
import struct
import time

from rig.machine_control.consts import SCPCommands, DataType, SDP_HEADER_LENGTH
from rig.machine_control.packets import SCPPacket
from rig.machine_control.scp_connection import SCPConnection, scpcall
from rig.machine_control import scp_connection


class SendReceive(object):
    def __init__(self, return_packet=None):
        self.last_seen = None
        self.return_packet = return_packet

    def send(self, packet, *args):
        self.last_seen = packet[:]

    def recv(self, *args, **kwargs):
        return self.return_packet(self.last_seen)


@pytest.fixture
def mock_conn():
    """Create an SCP connection with a mocked out socket.
    """
    # Create an SCPConnection pointed at localhost
    # Mock out the socket
    conn = SCPConnection("localhost", timeout=0.01)
    conn.sock = mock.Mock(spec_set=conn.sock)

    return conn


def test_scpcall():
    """scpcall is a utility for specifying SCP packets and callbacks"""
    call = scpcall(0, 1, 2, 3)
    assert call.x == 0
    assert call.y == 1
    assert call.p == 2
    assert call.cmd == 3
    assert call.arg1 == call.arg2 == call.arg3 == 0
    assert call.data == b''
    assert call.timeout == 0.0
    assert isinstance(call.callback, collections.Callable)


def test_single_scp_packet(mock_conn):
    # Replace send_scp_burst with a mock
    mock_conn.send_scp_burst = mock.Mock()
    packet = b'\x00' * (SDP_HEADER_LENGTH + 18)

    def send_burst(buffer_size, window_size, args):
        assert buffer_size == 512
        assert window_size == 1

        # Call the callback
        for i, arg in enumerate(args):
            assert i == 0  # Only one packet to send
            assert isinstance(arg, scpcall)
            assert arg.x == 0
            assert arg.y == 1
            assert arg.p == 2
            assert arg.cmd == 3
            assert arg.arg1 == 4
            assert arg.arg2 == 5
            assert arg.arg3 == 6
            assert arg.data == b'Hello'
            assert arg.timeout == 0.1

            arg.callback(packet)

    mock_conn.send_scp_burst.side_effect = send_burst

    # Send a single SCP packet, ensure these arguments are just passed with a
    # window_size of 1 to send_scp_burst.
    rp = mock_conn.send_scp(512, 0, 1, 2, 3, 4, 5, 6, b'Hello', 1, 0.1)
    assert isinstance(rp, SCPPacket)
    assert rp.arg1 is not None
    assert rp.arg2 is None
    assert rp.arg3 is None

    assert mock_conn.send_scp_burst.call_count == 1


class TestBursts(object):
    """Tests for transmitting bursts of SCP packets."""
    @pytest.mark.parametrize("buffer_size, receive_length",
                             [(128, 256), (509, 1024)])
    def test_single_packet(self, mock_conn, buffer_size, receive_length):
        """Test correct operation for transmitting and receiving a single
        packet.
        """
        callback = mock.Mock(name="callback")

        def packets():
            # Yield a single packet, with a callback
            yield scpcall(3, 5, 0, 12, callback=callback)

        sent_packet = SCPPacket(
            True, 0xff, 0, 0, 7, 31, 3, 5, 0, 0, 12, 0, 0, 0, 0, b'')

        # Create a mock socket object which will reply with a valid packet the
        # second time it is called.
        class ReturnPacket(object):
            def __init__(self):
                self.packet = None
                self.called = False

            def __call__(self, packet):
                if not self.called:
                    self.called = True
                    raise IOError

                self.packet = SCPPacket.from_bytestring(packet)
                assert self.packet.dest_x == 3
                assert self.packet.dest_y == 5
                assert self.packet.dest_cpu == 0
                assert self.packet.cmd_rc == 12

                self.packet.cmd_rc = 0x80
                return self.packet.bytestring

        return_packet = ReturnPacket()
        sr = SendReceive(return_packet)
        mock_conn.sock.send.side_effect = sr.send
        mock_conn.sock.recv.side_effect = sr.recv

        # Send the bursty packet, assert that it was sent and received and that
        # the callback was called.
        mock_conn.send_scp_burst(buffer_size, 8, packets())

        mock_conn.sock.send.assert_called_once_with(sent_packet.bytestring)
        mock_conn.sock.recv.assert_has_calls([mock.call(receive_length)] * 2)

        assert callback.call_count == 1
        assert (callback.call_args[0][0] == return_packet.packet.bytestring)

    def test_single_packet_times_out(self, mock_conn):
        """Test correct operation for transmitting a single packet which is
        never acknowledged.
        """
        # Create a callable for the socket send that asserts that we always
        # send the same packet.
        class Send(object):
            def __init__(self):
                self.last_packet = None

            def __call__(self, packet):
                if self.last_packet is None:
                    self.last_packet = packet
                else:
                    assert self.last_packet == packet

        mock_conn.sock.send.side_effect = Send()

        # Create a generator of packets to send
        def packets():
            # Yield a single packet
            yield scpcall(3, 5, 0, 12)

        # The socket will always return with an IOError, so the packet is never
        # acknowledged.
        mock_conn.sock.recv.side_effect = IOError

        # Send the bursty packet, assert that it was sent for as many times as
        # specified.
        start = time.time()
        with pytest.raises(scp_connection.TimeoutError):
            mock_conn.send_scp_burst(512, 8, packets())
        fail_time = time.time() - start

        # Failing to transmit should take some time
        assert fail_time >= mock_conn.n_tries * mock_conn.default_timeout

        # We shouldn't have transmitted the packet more than the number of
        # times we specified.
        assert mock_conn.sock.send.call_count == mock_conn.n_tries
        assert mock_conn.sock.recv.called

    @pytest.mark.parametrize("err_code", [0x8b, 0x8c, 0x8d, 0x8e])
    def test_single_packet_fails_with_RC_P2P_ERROR(self, mock_conn, err_code):
        """Test correct operation for transmitting a single packet which is
        always acknowledged with one of the RC_P2P error codes.
        """
        # Create a generator of packets to send
        def packets():
            # Yield a single packet
            yield scpcall(3, 5, 0, 12)

        # The socket will always return with a packet that indicates some
        # timeout or similar further down the pipeline, so the packet is never
        # acknowledged.
        mock_conn.sock.recv.return_value = SCPPacket(
            False, 0, 0, 0, 0, 0, 0, 0, 0, 0, err_code, 0).bytestring

        # Send the bursty packet, assert that it was sent for as many times as
        # specified.
        with pytest.raises(scp_connection.TimeoutError):
            mock_conn.send_scp_burst(512, 8, packets())

        # We shouldn't have transmitted the packet more than the number of
        # times we specified.
        assert mock_conn.sock.send.call_count == mock_conn.n_tries
        assert mock_conn.sock.recv.called

    def test_single_packet_times_out_with_extended_timeout(self, mock_conn):
        """Test correct operation for transmitting a single packet which is
        never acknowledged.
        """
        def packets():
            # Yield a single packet
            yield scpcall(3, 5, 0, 12, timeout=0.1)

        # The socket will always return with an IOError, so the packet is never
        # acknowledged.
        mock_conn.sock.recv.side_effect = IOError

        # Send the bursty packet, assert that it was sent for as many times as
        # specified.
        start = time.time()
        with pytest.raises(scp_connection.TimeoutError):
            mock_conn.send_scp_burst(512, 8, packets())
        fail_time = time.time() - start

        # Failing to transmit should take some time
        assert (fail_time >=
                mock_conn.n_tries * (mock_conn.default_timeout + 0.1))

        # We shouldn't have transmitted the packet more than the number of
        # times we specified.
        assert mock_conn.sock.send.call_count == mock_conn.n_tries
        assert mock_conn.sock.recv.called

    def test_seq_not_reused_for_outstanding_packet(self, mock_conn):
        """Test that a sequence index is never reused for a packet which
        receives no acknowledgement.
        """
        def packets():
            # Yield a single packet which we refuse to acknowledge (should have
            # seq==0)
            yield scpcall(0, 0, 0, 12)

            # Yield a large number of obviously different packets, the seq
            # (==0) should never be used for any of these.
            for _ in range(1000):
                yield scpcall(0, 0, 0, 2)

        # Create a mock socket object which will reply with a valid packet for
        # everything BUT seq==0
        class ReturnPacket(object):
            def __init__(self):
                self.ignore_seq = None
                self.called = False

            def __call__(self, packet):
                packet = SCPPacket.from_bytestring(packet)

                if self.ignore_seq is None:
                    self.ignore_seq = packet.seq

                if packet.seq == self.ignore_seq:
                    assert packet.cmd_rc == 12
                    raise IOError  # No packet to return
                else:
                    packet.cmd_rc = 0x80
                    return packet.bytestring

        return_packet = ReturnPacket()
        sr = SendReceive(return_packet)
        mock_conn.seq = scp_connection.seqs(0x1)
        mock_conn.sock.send.side_effect = sr.send
        mock_conn.sock.recv.side_effect = sr.recv

        # Send the packets, the one packet we refuse to ignore should timeout
        with pytest.raises(scp_connection.TimeoutError):
            mock_conn.send_scp_burst(512, 8, packets())

    @pytest.mark.parametrize(
        "rc, error",
        [(0x81, scp_connection.BadPacketLengthError),
         (0x83, scp_connection.InvalidCommandError),
         (0x84, scp_connection.InvalidArgsError),
         (0x87, scp_connection.NoRouteError),
         (0x00, Exception)])
    def test_errors(self, mock_conn, rc, error):
        """Test that errors are raised when error RCs are returned."""
        # Create an object which returns a packet with an error code
        class ReturnPacket(object):
            def __init__(self):
                self.packet = None

            def __call__(self, packet):
                self.packet = SCPPacket.from_bytestring(packet)
                self.packet.cmd_rc = rc
                self.packet.arg1 = None
                self.packet.arg2 = None
                self.packet.arg3 = None
                self.packet.data = b''
                return self.packet.bytestring

        return_packet = ReturnPacket()
        sr = SendReceive(return_packet)
        mock_conn.sock.send.side_effect = sr.send
        mock_conn.sock.recv.side_effect = sr.recv

        # Send an SCP command and check that the correct error is raised
        packets = [scpcall(3, 5, 0, 12)]
        with pytest.raises(error):
            mock_conn.send_scp_burst(256, 1, iter(packets))

    @pytest.mark.parametrize("window_size, n_tries", [(10, 2), (8, 5)])
    def test_fills_window(self, mock_conn, window_size, n_tries):
        """Test that when no acknowledgement packets are sent the window fills
        up and all packets are tried multiple times.
        """
        def packets():
            # Yield 10 packets
            for x in range(10):
                yield scpcall(10, 5, 0, 12)

        # Set the number of retries
        mock_conn.n_tries = n_tries

        # The socket will always return with an IOError, so the packet is never
        # acknowledged.
        mock_conn.sock.recv.side_effect = IOError

        # Send the bursty packet, assert that it was sent for as many times as
        # specified.
        with pytest.raises(scp_connection.TimeoutError):
            mock_conn.send_scp_burst(512, window_size, packets())

        # We should have transmitted AT LEAST one packet per window item and AT
        # MOST window size * number of tries packets.
        assert (window_size < mock_conn.sock.send.call_count <=
                window_size * n_tries)


@pytest.mark.parametrize(
    "buffer_size, window_size, x, y, p", [(128, 1, 0, 0, 1), (256, 5, 1, 2, 3)]
)
@pytest.mark.parametrize(
    "n_bytes, data_type, start_address",
    [(1, DataType.byte, 0x60000000),   # Only reading a byte
     (3, DataType.byte, 0x60000000),   # Can only read bytes
     (2, DataType.byte, 0x60000001),   # Offset from short
     (4, DataType.byte, 0x60000001),   # Offset from word
     (2, DataType.short, 0x60000002),  # Reading a short
     (6, DataType.short, 0x60000002),  # Can read shorts
     (4, DataType.short, 0x60000002),  # Offset from word
     (4, DataType.word, 0x60000004),   # Reading a word
     (257, DataType.byte, 0x60000001),
     (511, DataType.byte, 0x60000001),
     (258, DataType.byte, 0x60000001),
     (256, DataType.byte, 0x60000001),
     (258, DataType.short, 0x60000002),
     (514, DataType.short, 0x60000002),
     (516, DataType.short, 0x60000002),
     (256, DataType.word, 0x60000004)
     ])
def test_read(buffer_size, window_size, x, y, p, n_bytes,
              data_type, start_address):
    mock_conn = SCPConnection("localhost")

    # Construct the expected calls, and hence the expected return packets
    offset = start_address
    offsets = []
    lens = []
    length_bytes = n_bytes
    while length_bytes > 0:
        offsets += [offset]
        lens += [min((buffer_size, length_bytes))]
        offset += lens[-1]
        length_bytes -= lens[-1]

    assert len(lens) == len(offsets), "Test is broken"

    with mock.patch.object(mock_conn, "send_scp_burst") as send_scp_burst:
        # Set send_scp_burst up to call all the callbacks with some specified
        # value.
        class CallCallbacks(object):
            read_data = b''

            def __call__(self, buffer_size, window_size, args):
                for i, arg in enumerate(args):
                    assert arg.x == x and arg.y == y and arg.p == p
                    assert arg.cmd == SCPCommands.read
                    assert arg.arg1 == offsets[i]
                    assert arg.arg2 == lens[i]
                    assert arg.arg3 == data_type

                    mock_packet = mock.Mock(spec_set=['data'])
                    mock_packet.data = struct.pack("B", i) * arg.arg2
                    self.read_data += mock_packet.data
                    arg.callback(
                        b'\x00' * (6 + SDP_HEADER_LENGTH) + mock_packet.data
                    )

        ccs = CallCallbacks()
        send_scp_burst.side_effect = ccs

        # Read an amount of memory specified by the size.
        data = mock_conn.read(buffer_size, window_size, x, y, p,
                              start_address, n_bytes)
        assert data == ccs.read_data

    # send_burst_scp should have been called once, each element in the iterator
    # it is given should match the offsets and lengths we worked out
    # previously.
    assert send_scp_burst.call_count == 1
    assert send_scp_burst.call_args[0][0] == buffer_size
    assert send_scp_burst.call_args[0][1] == window_size


@pytest.mark.parametrize(
    "buffer_size, window_size, x, y, p",
    [(128, 1, 0, 0, 1), (256, 5, 1, 2, 3)]
)
@pytest.mark.parametrize(
    "start_address,data,data_type",
    [(0x60000000, b'\x1a', DataType.byte),
     (0x60000001, b'\xab', DataType.byte),
     (0x60000001, b'\x00\x00', DataType.byte),
     (0x60000001, b'\x00\x00\x00\x00', DataType.byte),
     (0x60000000, b'\x00\x00', DataType.short),
     (0x60000002, b'\x00\x00\x00\x00', DataType.short),
     (0x60000004, b'\x00\x00\x00\x00', DataType.word),
     (0x60000001, 512*b'\x00\x00\x00\x00', DataType.byte),
     (0x60000002, 512*b'\x00\x00\x00\x00', DataType.short),
     (0x60000000, 512*b'\x00\x00\x00\x00', DataType.word),
     ])
def test_write(buffer_size, window_size, x, y, p,
               start_address, data, data_type):
    mock_conn = SCPConnection("localhost")

    # Write the data
    with mock.patch.object(mock_conn, "send_scp_burst") as send_scp_burst:
        mock_conn.write(buffer_size, window_size, x, y, p, start_address, data)

    # Check that the correct calls to send_scp were made
    segments = []
    address = start_address
    addresses = []
    while len(data) > 0:
        addresses.append(address)
        segments.append(data[0:buffer_size])

        data = data[buffer_size:]
        address += len(segments[-1])

    # send_burst_scp should have been called once, each element in the iterator
    # it is given should match the offsets and lengths we worked out
    # previously.
    assert send_scp_burst.call_count == 1
    assert send_scp_burst.call_args[0][0] == buffer_size
    assert send_scp_burst.call_args[0][1] == window_size
    pars_calls = send_scp_burst.call_args[0][2]

    for args, addr, data in zip(pars_calls, addresses, segments):
        assert args.x == x and args.y == y and args.p == p
        assert args.cmd == SCPCommands.write
        assert args.arg1 == addr
        assert args.arg2 == len(data)
        assert args.arg3 == data_type
        assert args.data == data
