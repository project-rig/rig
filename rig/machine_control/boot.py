"""Boot constructs for a SpiNNaker machine.

.. warning::
    Implementation is reconstructed from a Perl implementation which forms a
    significant part of the documentation for this process.
"""
from . import struct_file
import enum
import pkg_resources
import socket
import struct
import time

# Specifies the size of packets that should be sent to SpiNNaker to boot the
# board, and to which port.
DTCM_SIZE = 32 * 1024
BOOT_BYTE_SIZE = 1024  # Block size for data in boot packets
BOOT_WORD_SIZE = BOOT_BYTE_SIZE / 4
BOOT_MAX_BLOCKS = DTCM_SIZE / BOOT_BYTE_SIZE
PORT = 54321
BOOT_DELAY = 0.01  # Pause between transmitting boot packets
POST_BOOT_DELAY = 2.0  # Delay to allow the boot to complete

# Specifies where in the boot data the struct containing default values should
# be written, and how many bytes of it should be written.
# NOTE I am assured by ST that writing into boot data bytes 384 onwards
# is unlikely to change in the foreseeable future.
BOOT_DATA_OFFSET = 3*128
BOOT_DATA_LENGTH = 128

# Boot options for different kinds of single-board SpiNNaker systems.
spin1_boot_options = {
    "width": 2, "height": 2, "hardware_version": 0,
    "led_config": 0x00076104,
}
spin2_boot_options = {
    "width": 2, "height": 2, "hardware_version": 2,
    "led_config": 0x00006103,
}
spin3_boot_options = {
    "width": 2, "height": 2, "hardware_version": 3,
    "led_config": 0x00000502,
}
spin4_boot_options = {
    "width": 8, "height": 8, "hardware_version": 4,
    "led_config": 0x00000001,
}
spin5_boot_options = {
    "width": 8, "height": 8, "hardware_version": 5,
    "led_config": 0x00000001,
}


def boot(hostname, width, height, cpu_frequency=200, hardware_version=0,
         led_config=0x00000001, boot_data=None, struct_data=None):
    """Boot a SpiNNaker machine of the given size.

    Parameters
    ----------
    hostname : str
        Hostname or IP address of the SpiNNaker chip to boot [as chip (0, 0)].
    width : int
        Width of the machine (0 < w < 256)
    height : int
        Height of the machine (0 < h < 256)
    cpu_frequency : int
        CPU clock-frequency.  **Note**: The default (200 MHz) is known
        safe.
    hardware_version : int
        Version number of the SpiNNaker boards used in the system (e.g. SpiNN-5
        boards would be 5). At the time of writing this value is ignored and
        can be safely set to the default value of 0.
    led_config : int
        Defines LED pin numbers for the SpiNNaker boards used in the system.
        The four least significant bits (3:0) give the number of LEDs. The next
        four bits give the pin number of the first LED, the next four the pin
        number of the second LED, and so forth. At the time of writing, all
        SpiNNaker board versions have their first LED attached to pin 0 and
        thus the default value of 0x00000001 is safe.
    boot_data : bytes or None
        Data to boot the machine with
    struct_data : bytes or None
        Data to interpret as a representation of the memory layout of data
        within the boot data.

    Notes
    -----
    The constants `rig.machine_control.boot.spinX_boot_options` can be used to
    specify boot parameters, for example::

        boot("board1", **spin5_boot_options)

    Will boot the Spin5 board connected with hostname "board1".
    """
    # Get the boot and struct data if not specified.
    if struct_data is None:
        struct_data = pkg_resources.resource_string("rig",
                                                    "boot/sark.struct")

    if boot_data is None:
        boot_data = pkg_resources.resource_string("rig", "boot/scamp.boot")

    # Read the struct file and modify the "sv" struct to contain the
    # configuration values and write this into the boot data.
    sv = struct_file.read_struct_file(struct_data)[b"sv"]
    sv.update_default_values(p2p_dims=(width << 8) | height,
                             hw_ver=hardware_version,
                             cpu_clk=cpu_frequency,
                             led0=led_config,
                             unix_time=int(time.time()),
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
    sock = socket.socket(type=socket.SOCK_DGRAM)
    sock.connect((hostname, PORT))

    # Transmit the boot data as a series of SDP packets.  First determine
    # how many blocks must be sent and transmit that, then transmit each
    # block.
    n_blocks = (len(buf) + BOOT_BYTE_SIZE - 1) // BOOT_BYTE_SIZE
    assert n_blocks <= BOOT_MAX_BLOCKS

    boot_packet(sock, BootCommand.start, arg3=n_blocks - 1)
    time.sleep(BOOT_DELAY)

    block = 0
    while len(boot_data) > 0:
        # Get the data to transmit
        data, boot_data = (boot_data[:BOOT_BYTE_SIZE],
                           boot_data[BOOT_BYTE_SIZE:])

        # Transmit, delay and increment the block count
        a1 = ((BOOT_WORD_SIZE - 1) << 8) | block
        boot_packet(sock, BootCommand.send_block, a1, data=data)
        time.sleep(BOOT_DELAY)
        block += 1

    # Send the END command
    boot_packet(sock, BootCommand.end, 1)

    # Close the socket and give time to boot
    sock.close()
    time.sleep(POST_BOOT_DELAY)


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
