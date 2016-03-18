"""Boot constructs for a SpiNNaker machine.

.. warning::
    Implementation is reconstructed from a Perl implementation which forms a
    significant part of the documentation for this process.
"""
from . import struct_file, consts
import enum
import pkg_resources
import socket
import struct
import time

from rig.utils.docstrings import add_int_enums_to_docstring

# Specifies the size of packets that should be sent to SpiNNaker to boot the
# board.
DTCM_SIZE = 32 * 1024
BOOT_BYTE_SIZE = 1024  # Block size for data in boot packets
BOOT_WORD_SIZE = BOOT_BYTE_SIZE // 4
BOOT_MAX_BLOCKS = DTCM_SIZE // BOOT_BYTE_SIZE

# Specifies where in the boot data the struct containing default values should
# be written, and how many bytes of it should be written.
# NOTE I am assured by ST that writing into boot data bytes 384 onwards
# is unlikely to change in the foreseeable future.
BOOT_DATA_OFFSET = 3*128
BOOT_DATA_LENGTH = 128

# Boot options for different kinds of single-board SpiNNaker systems.
spin1_boot_options = {
    "hw_ver": 1,
    "led0": 0x00076104,
}
"""Boot options for :py:func:`.boot` for SpiNN-1 boards."""

spin2_boot_options = {
    "hw_ver": 2,
    "led0": 0x00006103,
}
"""Boot options for :py:func:`.boot` for SpiNN-2 boards."""

spin3_boot_options = {
    "hw_ver": 3,
    "led0": 0x00000502,
}
"""Boot options for :py:func:`.boot` for SpiNN-3 boards."""

spin4_boot_options = {
    "hw_ver": 4,
    "led0": 0x00000001,
}
"""Boot options for :py:func:`.boot` for SpiNN-4 boards."""

spin5_boot_options = {
    "hw_ver": 5,
    "led0": 0x00000001,
}
"""Boot options for :py:func:`.boot` for SpiNN-5 boards."""


def boot(hostname, boot_port=consts.BOOT_PORT,
         scamp_binary=None, sark_struct=None,
         boot_delay=0.05, post_boot_delay=2.0,
         **sv_overrides):
    """Boot a SpiNNaker machine of the given size.

    Parameters
    ----------
    hostname : str
        Hostname or IP address of the SpiNNaker chip to use to boot the system.
    boot_port : int
        The port number to sent boot packets to.
    scamp_binary : filename or None
        Filename of the binary to boot the machine with or None to use the
        SC&MP binary bundled with Rig.
    sark_struct : filename or None
        The 'sark.struct' file which defines the datastructures or None to use
        the one bundled with Rig.
    boot_delay : float
        Number of seconds to pause between sending boot data packets.
    post_boot_delay : float
        Number of seconds to wait after sending last piece of boot data to give
        SC&MP time to re-initialise the Ethernet interface. Note that this does
        *not* wait for the system to fully boot.
    **sv_overrides : {name: value, ...}
        Any additional keyword arguments may be used to override the default
        values in the 'sv' struct defined in the struct file.

    Notes
    -----
    The constants `rig.machine_control.boot.spinX_boot_options` provide boot
    parameters for specific SpiNNaker board revisions, for example::

        boot("board1", **spin3_boot_options)

    Will boot the Spin3 board connected with hostname "board1".

    Returns
    -------
    {struct_name: :py:class:`~rig.machine_control.struct_file.Struct`}
        Layout of structs in memory.
    """
    # Get the boot data if not specified.
    scamp_binary = (scamp_binary if scamp_binary is not None else
                    pkg_resources.resource_filename("rig", "boot/scamp.boot"))
    sark_struct = (sark_struct if sark_struct is not None else
                   pkg_resources.resource_filename("rig", "boot/sark.struct"))
    with open(scamp_binary, "rb") as f:
        boot_data = f.read()

    # Read the struct file and modify the "sv" struct to contain the
    # configuration values and write this into the boot data.
    with open(sark_struct, "rb") as f:
        struct_data = f.read()
    structs = struct_file.read_struct_file(struct_data)
    sv = structs[b"sv"]
    sv.update_default_values(**sv_overrides)
    sv.update_default_values(unix_time=int(time.time()),
                             boot_sig=int(time.time()),
                             root_chip=1)
    struct_packed = sv.pack()
    assert len(struct_packed) >= 128  # Otherwise shoving this data in is nasty

    buf = bytearray(boot_data)
    buf[BOOT_DATA_OFFSET:BOOT_DATA_OFFSET+BOOT_DATA_LENGTH] = \
        struct_packed[:BOOT_DATA_LENGTH]
    assert len(buf) < DTCM_SIZE  # Assert that we fit in DTCM
    boot_data = bytes(buf)

    # Create a socket to communicate with the board
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((hostname, boot_port))

    # Transmit the boot data as a series of SDP packets.  First determine
    # how many blocks must be sent and transmit that, then transmit each
    # block.
    n_blocks = (len(buf) + BOOT_BYTE_SIZE - 1) // BOOT_BYTE_SIZE
    assert n_blocks <= BOOT_MAX_BLOCKS

    boot_packet(sock, BootCommand.start, arg3=n_blocks - 1)
    time.sleep(boot_delay)

    block = 0
    while len(boot_data) > 0:
        # Get the data to transmit
        data, boot_data = (boot_data[:BOOT_BYTE_SIZE],
                           boot_data[BOOT_BYTE_SIZE:])

        # Transmit, delay and increment the block count
        a1 = ((BOOT_WORD_SIZE - 1) << 8) | block
        boot_packet(sock, BootCommand.send_block, a1, data=data)
        time.sleep(boot_delay)
        block += 1

    # Send the END command
    boot_packet(sock, BootCommand.end, 1)

    # Close the socket and give time to boot
    sock.close()
    time.sleep(post_boot_delay)

    return structs


def boot_packet(sock, cmd, arg1=0, arg2=0, arg3=0, data=b""):
    """Create and transmit a packet to boot the machine.

    Parameters
    ----------
    sock : :py:class:`~socket.socket`
        Connected socket to use to transmit the packet.
    cmd : int
    arg1 : int
    arg2 : int
    arg3 : int
    data : :py:class:`bytes`
        Optional data to include in the packet.
    """
    PROTOCOL_VERSION = 1

    # Generate the (network-byte order) header
    header = struct.pack("!H4I", PROTOCOL_VERSION, cmd, arg1, arg2, arg3)

    assert len(data) % 4 == 0  # Data should always be word-sized
    fdata = b""

    # Format the data from little- to network-/big-endian
    while len(data) > 0:
        word, data = (data[:4], data[4:])
        fdata += struct.pack("!I", struct.unpack("<I", word)[0])

    # Transmit the packet
    sock.send(header + fdata)


@add_int_enums_to_docstring
class BootCommand(enum.IntEnum):
    """Boot packet command numbers"""

    start = 1
    """Boot data begin.

    Parameters
    ----------
    arg1 : unused
    arg2 : unused
    arg3 : int
        Number of boot data blocks to be sent - 1.
    """

    send_block = 3
    """Send a block of boot data.

    Parameters
    ----------
    arg1 : unused
        32-bit value with:

        * Bits 7:0 containing the block number being sent.
        * Bits 31:8 The number of 32-bit words in the block being sent - 1.
    arg2 : unused
    arg3 : unused
    """

    end = 5
    """End of boot data.

    Parameters
    ----------
    arg1 : int
        The value '1'.
    arg2 : unused
    arg3 : unused
    """
