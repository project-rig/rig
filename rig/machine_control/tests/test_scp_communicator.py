import mock
import pytest
import time

from ..scp_communicator import SCPCommunicator
from .. import scp_communicator


@pytest.fixture(scope='module')
def comms(spinnaker_ip):
    return SCPCommunicator(spinnaker_ip)


@pytest.fixture
def mock_comms():
    # Create the file-like object
    comms = mock.Mock(spec=SCPCommunicator)

    # Return NULLs for reads
    comms.read.side_effect = \
        lambda x, y, p, address, length_bytes, data_type: b'\x00'*length_bytes

    return comms


@pytest.mark.spinnaker
def test_sver(comms):
    """Test getting the software version data."""
    # (Assuming a 4-node board) Get the software version for a number of cores.
    for x in range(2):
        for y in range(2):
            for p in range(16):
                sver = comms.software_version(x, y, p)
                assert sver.virt_cpu == p
                assert "SpiNNaker" in sver.version_string
                assert sver.version >= 1.3


@pytest.mark.spinnaker
@pytest.mark.parametrize("action", [scp_communicator.LEDAction.ON,
                                    scp_communicator.LEDAction.OFF,
                                    scp_communicator.LEDAction.TOGGLE,
                                    scp_communicator.LEDAction.TOGGLE])
def test_set_led(comms, action):
    """Test getting the software version data."""
    # (Assuming a 4-node board)
    for x in range(2):
        for y in range(2):
            comms.set_led(x, y, 1, action)

    time.sleep(0.05)


@pytest.mark.spinnaker
def test_write_and_read(comms):
    """Test write and read capabilities by writing a string to SDRAM and then
    reading back in a different order.
    """
    data = b'Hello, SpiNNaker'

    # You put the data in
    comms.write(0, 0, 0, 0x70000000, data[0:4],
                scp_communicator.DataType.WORD)
    comms.write(0, 0, 0, 0x70000004, data[4:6],
                scp_communicator.DataType.SHORT)
    comms.write(0, 0, 0, 0x70000006, data[6:],
                scp_communicator.DataType.BYTE)

    # You take the data out
    assert comms.read(0, 0, 1, 0x70000000, 1,
                      scp_communicator.DataType.BYTE) == data[0]
    assert comms.read(0, 0, 1, 0x70000000, 2,
                      scp_communicator.DataType.SHORT) == data[0:2]
    assert comms.read(0, 0, 1, 0x70000000, 4,
                      scp_communicator.DataType.WORD) == data[0:4]

    # Read out the entire string
    assert comms.read(0, 0, 1, 0x70000000, len(data),
                      scp_communicator.DataType.BYTE) == data
    assert comms.read(0, 0, 1, 0x70000000, len(data),
                      scp_communicator.DataType.SHORT) == data
    assert comms.read(0, 0, 1, 0x70000000, len(data),
                      scp_communicator.DataType.WORD) == data


@pytest.mark.spinnaker
def test_set_get_clear_iptag(comms):
    # Get our address, then add a new IPTag pointing
    ip_addr = comms.sock.getsockname()[0]
    port = 1234
    iptag = 7

    # Set IPTag 7 with the parameters from above
    comms.iptag_set(0, 0, iptag, ip_addr, port)

    # Get the IPtag and check that it is as we set it
    ip_tag = comms.iptag_get(0, 0, iptag)
    assert ip_addr == ip_tag.addr
    assert port == ip_tag.port
    assert ip_tag.flags != 0

    # Clear the IPTag
    comms.iptag_clear(0, 0, iptag)

    # Check that it is empty by inspecting the flag
    ip_tag = comms.iptag_get(0, 0, iptag)
    assert ip_tag.flags == 0


@pytest.mark.spinnaker
def test_bad_packet_length(comms):
    """Test transmitting a packet with an incorrect length, this should raise
    an error.
    """
    with pytest.raises(scp_communicator.BadPacketLengthError):
        comms._send_scp(0, 0, 0, 0, None, None, None, b'')


@pytest.mark.spinnaker
def test_invalid_command(comms):
    """Test transmitting a packet with an invalid CMD raises an error."""
    # Create an SCPCommunicator for the given SpiNNaker IP address.
    with pytest.raises(scp_communicator.InvalidCommandError):
        comms._send_scp(0, 0, 0, 6)


"""
@pytest.mark.spinnaker
def test_invalid_argument(spinnaker_ip):
    # Create an SCPCommunicator for the given SpiNNaker IP address.
    comms = SCPCommunicator(spinnaker_ip)

    with pytest.raises(scp_communicator.InvalidArgsError):
        comms._send_scp(0, 0, 0, scp_communicator.SCPCommands.LED, 128)
"""


@pytest.mark.parametrize(
    "n_bytes,data_type,start_address",
    [(1, scp_communicator.DataType.BYTE, 0x70000000),   # Only reading a byte
     (3, scp_communicator.DataType.BYTE, 0x70000000),   # Can only read bytes
     (2, scp_communicator.DataType.BYTE, 0x70000001),   # Offset from short
     (4, scp_communicator.DataType.BYTE, 0x70000001),   # Offset from word
     (2, scp_communicator.DataType.SHORT, 0x70000002),  # Reading a short
     (6, scp_communicator.DataType.SHORT, 0x70000002),  # Can read shorts
     (4, scp_communicator.DataType.SHORT, 0x70000002),  # Offset from word
     (4, scp_communicator.DataType.WORD, 0x70000004)    # Reading a word
     ])
def test_sdram_file_read_single_packet(mock_comms, n_bytes, data_type,
                                       start_address):
    f = scp_communicator.SDRAMFile(mock_comms, x=0, y=0,
                                   start_address=start_address)

    # Read an amount of memory specified by the size
    data = f.read(n_bytes)
    assert len(data) == n_bytes

    # Assert that a call was made to the communicator with the correct
    # parameters.
    mock_comms.read.assert_called_once_with(0, 0, 0, start_address, n_bytes,
                                            data_type)


@pytest.mark.parametrize(
    "n_bytes,data_type,start_address,n_packets",
    [(257, scp_communicator.DataType.BYTE, 0x70000001, 2),
     (511, scp_communicator.DataType.BYTE, 0x70000001, 2),
     (258, scp_communicator.DataType.BYTE, 0x70000001, 2),
     (256, scp_communicator.DataType.BYTE, 0x70000001, 1),
     (258, scp_communicator.DataType.SHORT, 0x70000002, 2),
     (514, scp_communicator.DataType.SHORT, 0x70000002, 3),
     (516, scp_communicator.DataType.SHORT, 0x70000002, 3),
     (256, scp_communicator.DataType.WORD, 0x70000004, 1)
     ])
def test_sdram_file_read_multiple_packets(mock_comms, n_bytes, data_type,
                                          start_address, n_packets):
    # Create the file-like object
    f = scp_communicator.SDRAMFile(mock_comms, x=0, y=0,
                                   start_address=start_address)

    # Read an amount of memory specified by the size.
    data = f.read(n_bytes)
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

    mock_comms.read.assert_has_calls(
        [mock.call(0, 0, 0, o, l, data_type) for (o, l) in
         zip(offsets, lens)]
    )


def test_sdram_file_read_subsequent(mock_comms):
    """Check that subsequent reads increment the offset."""
    start_address = 0x70000000
    f = scp_communicator.SDRAMFile(mock_comms, 0, 0, start_address)

    f.read(1)
    mock_comms.read.assert_called_with(0, 0, 0, start_address, 1,
                                       scp_communicator.DataType.BYTE)
    f.read(2)
    mock_comms.read.assert_called_with(0, 0, 0, start_address + 1, 2,
                                       scp_communicator.DataType.BYTE)


@pytest.mark.parametrize(
    "start_address,data,data_type",
    [(0x70000000, b'\x00', scp_communicator.DataType.BYTE),
     (0x70000001, b'\x00', scp_communicator.DataType.BYTE),
     (0x70000001, b'\x00\x00', scp_communicator.DataType.BYTE),
     (0x70000001, b'\x00\x00\x00\x00', scp_communicator.DataType.BYTE),
     (0x70000000, b'\x00\x00', scp_communicator.DataType.SHORT),
     (0x70000002, b'\x00\x00\x00\x00', scp_communicator.DataType.SHORT),
     (0x70000004, b'\x00\x00\x00\x00', scp_communicator.DataType.WORD),
     (0x70000000, 512*b'\x00\x00\x00\x00', scp_communicator.DataType.WORD),
     ])
def test_sdram_file_write(mock_comms, start_address, data, data_type):
    # Create the file-like object
    f = scp_communicator.SDRAMFile(mock_comms, 0, 0, start_address)

    # Write the data
    f.write(data)

    # Check that the correct calls to write were made
    segments = []
    address = start_address
    addresses = []
    while len(data) > 0:
        addresses.append(address)
        segments.append(data[0:256])

        data = data[256:]
        address += len(segments[-1])

    mock_comms.write.assert_has_calls(
        [mock.call(0, 0, 0, a, d, data_type) for (a, d) in
         zip(addresses, segments)]
    )


def test_sdram_read_beyond(mock_comms):
    """Test that any attempt to read beyond the range of SDRAM results in a
    shortened string.
    """
    f = scp_communicator.SDRAMFile(mock_comms, 0, 0, 0, 4)
    data = f.read(8)
    assert len(data) == 5
    mock_comms.read.assert_called_once_with(0, 0, 0, 0, 5,
                                            scp_communicator.DataType.BYTE)


def test_sdram_write_beyond(mock_comms):
    """Test that any attempt to write beyond the range of SDRAM results in an
    EOFError being raised.
    """
    f = scp_communicator.SDRAMFile(mock_comms, 0, 0, 0, 4)

    with pytest.raises(EOFError):
        f.write(8*'\x00')

    assert not mock_comms.write.called


def test_seek(mock_comms):
    # Create the file-like object
    f = scp_communicator.SDRAMFile(mock_comms, 0, 0)
    addr = f.address

    # Seek forward one
    f.seek(1)
    assert f.address == addr + 1

    # Seek backward one
    f.seek(-1)
    assert f.address == addr
