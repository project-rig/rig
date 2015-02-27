"""Constants used in the SCP protocol.
"""
import enum

SCP_PORT = 17893  # TODO Reference spec
# The smallest power of two large enough to handle the largest packet the
# SpiNNaker SDP implementation can produce (256+8 bytes).
SCP_RECEIVE_LENGTH = 512


class SCPCommands(enum.IntEnum):
    """Command codes used in SCP packets."""
    sver = 0  # Get the software version
    read = 2  # Read data
    write = 3  # Write data

    led = 25  # Change the state of an LED
    iptag = 26  # Change/clear/get the value of an IPTag

    alloc_free = 28  # Allocate or free SDRAM and routing_table entries


class DataType(enum.IntEnum):
    """Used to specify the size of data being read to/from a SpiNNaker machine
    over SCP.
    """
    byte = 0
    short = 1
    word = 2


class LEDAction(enum.IntEnum):
    """Indicate the action that should be applied to a given LED."""
    on = 3
    off = 2
    toggle = 1


class IPTagCommands(enum.IntEnum):
    """Indicate the action that should be performed to the given IPTag."""
    set = 1
    get = 2
    clear = 3


class AllocOperations(enum.IntEnum):
    """Used to allocate or free regions of SDRAM and routing table entries."""
    alloc_sdram = 0  # Allocate a region of SDRAM
    free_sdram_by_ptr = 1  # Free a region of SDRAM with a pointer
    free_sdram_by_tag = 2  # Free a region of SDRAM with a tag and app_id

    alloc_rtr = 3  # Allocate a region of routing table entries
    free_rtr_by_pos = 4  # Free routing table entries by index
    free_rtr_by_app = 5  # Free routing table entries by app_id
