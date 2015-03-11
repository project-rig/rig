import mock
from mock import call
import pytest

from ..packets import SCPPacket
from ..scp_connection import SCPConnection
from .. import scp_connection


class SendReceive(object):
    def __init__(self, return_packet=None):
        self.last_seen = None
        self.return_packet = return_packet

    def send(self, packet, *args):
        self.last_seen = packet[2:]

    def recv(self, *args, **kwargs):
        return b"\x00\x00" + self.return_packet(self.last_seen)


@pytest.fixture
def mock_conn():
    """Create an SCP connection with a mocked out socket.
    """
    # Create an SCPConnection pointed at localhost
    # Mock out the socket
    conn = SCPConnection("localhost", timeout=0.01)
    conn.sock = mock.Mock(spec_set=conn.sock)

    return conn


@pytest.mark.parametrize("bufsize, recv_size", [(232, 512), (256, 512),
                                                (248, 512), (504, 512),
                                                (514, 1024)])
def test_success(mock_conn, bufsize, recv_size):
    """Test successfully transmitting and receiving, where the seq of the first
    returned packet is wrong.
    """
    # Generate the return packet
    class ReturnPacket(object):
        def __init__(self):
            self.d = False

        def __call__(self, last):
            if not self.d:
                self.d = True

                # Change the sequence value
                pkg = SCPPacket.from_bytestring(last)
                pkg.seq += 1
                return pkg.bytestring
            else:
                return last

    sr = SendReceive(ReturnPacket())

    # Set up the mock connections
    mock_conn.sock.send.side_effect = sr.send
    mock_conn.sock.recv.side_effect = sr.recv

    # Send and receive
    recvd = mock_conn.send_scp(bufsize, 1, 2, 3, 4, 5, 6, 7, b'\x08')
    assert isinstance(recvd, SCPPacket)

    # Check that the transmitted packet was sane, and that only two packets
    # were transmitted (because the first was acknowledged with an incorrect
    # sequence number).  Also assert that there were only 2 calls to recv and
    # that they were of the correct size.
    assert mock_conn.sock.send.call_count == 2
    mock_conn.sock.recv.assert_has_calls([call(recv_size)] * 2)
    transmitted = SCPPacket.from_bytestring(sr.last_seen)
    assert transmitted.dest_x == recvd.dest_x == 1
    assert transmitted.dest_y == recvd.dest_y == 2
    assert transmitted.dest_cpu == recvd.dest_cpu == 3
    assert transmitted.cmd_rc == recvd.cmd_rc == 4
    assert transmitted.arg1 == recvd.arg1 == 5
    assert transmitted.arg2 == recvd.arg2 == 6
    assert transmitted.arg3 == recvd.arg3 == 7
    assert transmitted.data == recvd.data == b'\x08'


@pytest.mark.parametrize("n_tries", [5, 2])
def test_retries(mock_conn, n_tries):
    mock_conn.sock.recv.side_effect = IOError
    mock_conn.n_tries = n_tries

    # Send an SCP command and check that an error is raised
    with pytest.raises(scp_connection.TimeoutError):
        mock_conn.send_scp(256, 0, 0, 0, 0)

    # Check that n attempts were made
    assert mock_conn.sock.send.call_count == n_tries


@pytest.mark.parametrize(
    "rc, error",
    [(0x81, scp_connection.BadPacketLengthError),
     (0x83, scp_connection.InvalidCommandError),
     (0x84, scp_connection.InvalidArgsError),
     (0x87, scp_connection.NoRouteError)])
def test_errors(mock_conn, rc, error):
    """Test that errors are raised when error RCs are returned."""
    def return_packet(last):
        packet = SCPPacket.from_bytestring(last)
        packet.cmd_rc = rc
        return packet.bytestring

    sr = SendReceive(return_packet)
    mock_conn.sock.send.side_effect = sr.send
    mock_conn.sock.recv.side_effect = sr.recv

    # Send an SCP command and check that the correct error is raised
    with pytest.raises(error):
        mock_conn.send_scp(256, 0, 0, 0, 0)

    assert mock_conn.sock.send.call_count == 1
    assert mock_conn.sock.recv.call_count == 1
