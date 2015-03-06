"""Constants used in the SCP protocol.
"""
import enum

SCP_PORT = 17893  # TODO Reference spec
SCP_RECEIVE_LENGTH = 512
"""The smallest power of two large enough to handle the largest packet the
SpiNNaker SDP implementation can produce (256+8 bytes).
"""

SCP_DATA_LENGTH = 256
"""Length of data that can be inserted into an SCP packet."""


class SCPCommands(enum.IntEnum):
    """Command codes used in SCP packets."""
    sver = 0  # Get the software version
    read = 2  # Read data
    write = 3  # Write data

    nearest_neighbour_packet = 20  # Send a nearest neighbour packet
    signal = 22  # Transmit a signal to applications
    flood_fill_data = 23  # Transmit flood-fill data

    led = 25  # Change the state of an LED
    iptag = 26  # Change/clear/get the value of an IPTag

    alloc_free = 28  # Allocate or free SDRAM and routing_table entries
    router = 29  # Router related commands


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


class RouterOperations(enum.IntEnum):
    """Operations that may be performed to the router."""
    init = 0
    clear = 1
    load = 2
    fixed_route_set_get = 3


class NNCommands(enum.IntEnum):
    """Nearest Neighbour operations."""
    flood_fill_start = 6
    flood_fill_end = 15


class NNConstants(enum.IntEnum):
    """Constants for use with nearest neighbour commands."""
    forward = 0x3f  # Forwarding configuration
    retry = 0x18  # Retry configuration


class AppFlags(enum.IntEnum):
    """Flags for application loading."""
    wait = 0x01


class AppState(enum.IntEnum):
    """States that an application may be in."""
    # Error states - further information may be available
    dead = 0
    power_down = 1
    runtime_exception = 2
    watchdog = 3

    # General states
    init = 4  # Transitory "(hopefully)"
    wait = 5  # Awaiting signal AppSignal.start (due to AppFlags.wait)
    c_main = 6  # Entered c_main
    run = 7  # Running application event loop
    pause = 10  # Paused by signal AppSignal.pause
    exit = 11  # Application returned from c_main
    idle = 15  # Prior to application loading

    # Awaiting synchronisation (at a barrier)
    sync0 = 8
    sync1 = 9


class AppSignal(enum.IntEnum):
    """Signals that may be transmitted to applications."""
    # General purpose signals
    init = 0  # (Re-)load default application (i.e. SARK)
    power_down = 1  # Power down cores.
    stop = 2  # Forcefully stop and cleanup an application
    start = 3  # Start applications in AppState.wait
    pause = 6  # Pause execution of an application
    cont = 7  # Continue execution after pausing
    exit = 8  # Request that an application terminate (drop to AppState.exit)
    timer = 9  # Manually trigger a timer interrupt

    # Barrier synchronisation
    sync0 = 4  # Continue from AppState.sync0
    sync1 = 5  # Continue from AppState.sync1

    # User defined signals
    usr0 = 10
    usr1 = 11
    usr2 = 12
    usr3 = 13


class AppDiagnosticSignal(enum.IntEnum):
    """Signals which interrogate the state of a machine.

    Note that a value is returned when any of these signals is sent.
    """
    OR = 16  # Is ANY core in a given state
    AND = 17  # Are ALL cores in a given state
    count = 18  # How many cores are in a state


class MessageType(enum.IntEnum):
    """Internally used to specify the type of a message."""
    multicast = 0
    peer_to_peer = 1
    nearest_neighbour = 2


signal_types = {
    AppSignal.init: MessageType.nearest_neighbour,
    AppSignal.power_down: MessageType.nearest_neighbour,
    AppSignal.start: MessageType.nearest_neighbour,
    AppSignal.stop: MessageType.nearest_neighbour,
    AppSignal.exit: MessageType.nearest_neighbour,

    AppSignal.sync0: MessageType.multicast,
    AppSignal.sync1: MessageType.multicast,
    AppSignal.pause: MessageType.multicast,
    AppSignal.cont: MessageType.multicast,
    AppSignal.timer: MessageType.multicast,
    AppSignal.usr0: MessageType.multicast,
    AppSignal.usr1: MessageType.multicast,
    AppSignal.usr2: MessageType.multicast,
    AppSignal.usr3: MessageType.multicast,

    AppDiagnosticSignal.AND: MessageType.peer_to_peer,
    AppDiagnosticSignal.OR: MessageType.peer_to_peer,
    AppDiagnosticSignal.count: MessageType.peer_to_peer,
}
"""Mapping from an :py:class:`.AppSignal` to the :py:class:`.MessageType`
used to transmit it.
"""
