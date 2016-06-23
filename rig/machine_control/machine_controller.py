"""A high level interface for controlling a SpiNNaker system."""

import collections
import functools
import os
import six
from six import iteritems
import socket
import struct
import time
import pkg_resources
import warnings

from rig.machine_control.consts import \
    SCPCommands, NNCommands, NNConstants, AppFlags, LEDAction
from rig.machine_control import boot, consts, regions, struct_file
from rig.machine_control.scp_connection import SCPConnection, SCPError
from rig.machine_control.common import unpack_sver_response_version

from rig import routing_table

from rig.links import Links

from rig.geometry import spinn5_eth_coords, spinn5_local_eth_coord

from rig.utils.contexts import ContextMixin, Required
from rig.utils.docstrings import add_signature_to_docstring


class MachineController(ContextMixin):
    """A high-level interface for controlling a SpiNNaker system.

    This class is essentially a wrapper around key functions provided by the
    SCP protocol which aims to straight-forwardly handle many of the difficult
    details and corner cases to ensure easy, efficient and reliable
    communication with and control of a SpiNNaker machine. A :ref:`tutorial
    <MachineController-tutorial>` is available for new users.

    Key features at a glance:

    * Machine booting
    * Probing for available resources
    * (Efficient & reliable) loading of applications
    * Application monitoring and control
    * Allocation and loading of routing tables
    * Allocation and loading of memory
    * An optional file-like interface to memory blocks
    * Setting up IPTags
    * Easy-to-use blocking API

    Coming soon:

    * (Additional) 'advanced' non-blocking, parallel I/O interface
    * (Automagically) handling multiple connections simultaneously

    This class does *not* provide any methods for sending and receiving
    arbitrary SDP packets to and from applications. For this you should use
    :py:mod:`sockets <socket>` and the :py:mod:`rig.machine_control.packets`
    library (for which a :ref:`tutorial <scp-and-sdp-tutorial>` is also
    available).

    This class features a context system which allows commonly required
    arguments to be specified for a whole block of code using a 'with'
    statement, for example::

        cm = MachineController("spinnaker")

        # Commands should refer to chip (2, 3)
        with cm(x=2, y=3):
            three_kb_of_joy = cm.sdram_alloc(3*1024)
            cm.write(three_kb_of_joy, b"joy" * 1024)
            core_one_status = cm.get_processor_status(1)

    """
    def __init__(self, initial_host, scp_port=consts.SCP_PORT,
                 boot_port=consts.BOOT_PORT, n_tries=5, timeout=0.5,
                 structs=None, initial_context={"app_id": 66}):
        """Create a new controller for a SpiNNaker machine.

        Parameters
        ----------
        initial_host : string
            Hostname or IP address of the SpiNNaker chip to connect to. If the
            board has not yet been booted, this will be used to boot the
            machine.
        scp_port : int
            Port number for SCP connections.
        boot_port : int
            Port number for booting the board.
        n_tries : int
            Number of SDP packet retransmission attempts.
        timeout : float
            Timeout in seconds before an SCP response is assumed lost and the
            request is retransmitted.
        structs : dict or None
            A dictionary of struct data defining the memory locations of
            important values in SARK as produced by
            :py:class:`rig.machine_control.struct_file.read_struct_file`. If
            None, the default struct file will be used.
        initial_context : `{argument: value}`
            Default argument values to pass to methods in this class. By
            default this just specifies a default App-ID.
        """
        # Initialise the context stack
        ContextMixin.__init__(self, initial_context)

        # Store the initial parameters
        self.initial_host = initial_host
        self.scp_port = scp_port
        self.boot_port = boot_port
        self.n_tries = n_tries
        self.timeout = timeout
        self._nn_id = 0  # ID for nearest neighbour packets
        self._scp_data_length = None
        self._window_size = None
        self._root_chip = None

        # Load default structs if none provided
        self.structs = structs
        if self.structs is None:
            struct_data = pkg_resources.resource_string("rig",
                                                        "boot/sark.struct")
            self.structs = struct_file.read_struct_file(struct_data)

        # This dictionary contains a lookup from chip (x, y) to the
        # SCPConnection associated with that chip. The special entry with the
        # key None is reserved for the connection initially made to the
        # machine and is special since it is always known to exist but its
        # actual position in the network is unknown.
        self.connections = {
            None: SCPConnection(initial_host, scp_port, n_tries, timeout)
        }

        # The dimensions of the system. This is set by discover_connections()
        # and is used by _get_connection to determine which of the above
        # connections to use.
        self._width = None
        self._height = None

    def __call__(self, **context_args):
        """For use with `with`: set default argument values.

        E.g::

            with controller(x=3, y=4):
                # All commands in this block now communicate with chip (3, 4)
        """
        return self.get_new_context(**context_args)

    @property
    def scp_data_length(self):
        """The maximum SCP data field length supported by the machine
        (bytes).
        """
        # If not known, query the machine
        if self._scp_data_length is None:
            data = self.get_software_version(255, 255, 0)
            self._scp_data_length = data.buffer_size
        return self._scp_data_length

    @property
    def scp_window_size(self):
        """The maximum number of packets that can be sent to a SpiNNaker board
        without receiving any acknowledgement packets.
        """
        # If not known, return the default
        # TODO: Query the machine
        if self._window_size is None:
            return 1
        return self._window_size

    @property
    def root_chip(self):
        """The coordinates (x, y) of the chip used to boot the machine."""
        # If not known, query the machine
        if self._root_chip is None:
            self._root_chip = self.get_software_version(255, 255, 0).position
        return self._root_chip

    @ContextMixin.use_contextual_arguments(
        x=Required, y=Required, p=Required)
    def send_scp(self, *args, **kwargs):
        """Transmit an SCP Packet and return the response.

        This function is a thin wrapper around
        :py:meth:`rig.machine_control.scp_connection.SCPConnection.send_scp`.

        This function will attempt to use the SCP connection nearest the
        destination of the SCP command if multiple connections have been
        discovered using :py:meth:`.discover_connections`.

        Parameters
        ----------
        x : int
        y : int
        p : int
        *args
        **kwargs
        """
        # Retrieve contextual arguments from the keyword arguments.  The
        # context system ensures that these values are present.
        x = kwargs.pop("x")
        y = kwargs.pop("y")
        p = kwargs.pop("p")
        return self._send_scp(x, y, p, *args, **kwargs)

    def _get_connection(self, x, y):
        """Get the appropriate connection for a chip."""
        if (self._width is None or self._height is None or
                self._root_chip is None):
            return self.connections[None]
        else:
            # If possible, use the local Ethernet connected chip
            eth_chip = spinn5_local_eth_coord(x, y, self._width, self._height,
                                              *self._root_chip)
            conn = self.connections.get(eth_chip)
            if conn is not None:
                return conn
            else:
                # If no connection was available to the local board, choose
                # another arbitrarily.
                # XXX: This choice will cause lots of contention in systems
                # with many missing Ethernet connections.
                return self.connections[None]

    def _send_scp(self, x, y, p, *args, **kwargs):
        """Determine the best connection to use to send an SCP packet and use
        it to transmit.

        This internal version of the method is identical to send_scp except it
        has positional arguments for x, y and p.

        See the arguments for
        :py:meth:`~rig.machine_control.scp_connection.SCPConnection` for
        details.
        """
        # Determine the size of packet we expect in return, this is usually the
        # size that we are informed we should expect by SCAMP/SARK or else is
        # the default.
        if self._scp_data_length is None:
            length = consts.SCP_SVER_RECEIVE_LENGTH_MAX
        else:
            length = self._scp_data_length

        connection = self._get_connection(x, y)
        return connection.send_scp(length, x, y, p, *args, **kwargs)

    def boot(self, width=None, height=None,
             only_if_needed=True, check_booted=True, **boot_kwargs):
        """Boot a SpiNNaker machine.

        The system will be booted from the Ethernet connected chip whose
        hostname was given as the argument to the MachineController. With the
        default arguments this method will only boot systems which have not
        already been booted and will wait until machine is completely booted
        (and raise a :py:exc:`.SpiNNakerBootError` on failure).

        This method uses :py:func:`rig.machine_control.boot.boot` to send boot
        commands to the machine and update the struct files contained within
        this object according to those used during boot.

        .. warning::

            Booting the system over the open internet is likely to fail due to
            the port number being blocked by most ISPs and UDP not being
            reliable. A proxy such as `spinnaker_proxy
            <https://github.com/project-rig/spinnaker_proxy>`_ may be useful in
            this situation.

        Parameters
        ----------
        width, height : *Deprecated*
            **Deprecated.** In older versions of SC&MP, it was necessary to
            indicate the size of the machine being booted. These parameters are
            now ignored and setting them will produce a deprecation warning.
        scamp_binary : filename or None
            Filename of the binary to boot the machine with or None to use the
            SC&MP binary bundled with Rig.
        sark_struct : filename or None
            The 'sark.struct' file which defines the datastructures or None to
            use the one bundled with Rig.
        boot_delay : float
            Number of seconds to pause between sending boot data packets.
        post_boot_delay : float
            Number of seconds to wait after sending last piece of boot data to
            give SC&MP time to re-initialise the Ethernet interface.
        only_if_needed : bool
            If ``only_if_needed`` is True (the default), this method checks to
            see if the machine is already booted and only attempts to boot the
            machine if neccessary.

            If ``only_if_needed`` is False, the boot commands will be sent to
            the target machine without checking if it is already booted or not.

            .. warning::

                If the machine has already been booted, sending the boot
                commands again will not 'reboot' the machine with the newly
                supplied boot image, even if ``only_if_needed`` is False.
        check_booted : bool
            If ``check_booted`` is True this method waits for the machine to be
            fully booted before returning. If False, this check is skipped and
            the function returns as soon as the machine's Ethernet interface is
            likely to be up (but not necessarily before booting has completed).
        **sv_overrides : {name: value, ...}
            Any additional keyword arguments may be used to override the
            default values in the 'sv' struct defined in the struct file.

        Returns
        -------
        bool
            Returns True if the machine was sent boot commands, False if the
            machine was already booted.

        Raises
        ------
        rig.machine_control.machine_controller.SpiNNakerBootError
            Raised when ``check_booted`` is True and the boot process was
            unable to boot the machine. Also raised when ``only_if_needed`` is
            True and the remote host is a BMP.

        Notes
        -----
        The constants `rig.machine_control.boot.spinX_boot_options` can be used
        to specify boot parameters, for example::

            controller.boot(**spin3_boot_options)

        This is neccessary on boards such as SpiNN-3 boards if the more than
        LED 0 are required by an application since by default, only LED 0 is
        enabled.
        """
        # Report deprecated width/height arguments
        if width is not None or height is not None:
            warnings.warn("Machine width and height are no longer needed when "
                          "booting a machine.", DeprecationWarning)

        # Check to see if the machine is already booted first
        if only_if_needed:
            # We create a new MachineController which fails quickly if it
            # doesn't receieve a reply (since typically the machine is already
            # booted).
            quick_fail_mc = MachineController(self.initial_host, n_tries=1)
            try:
                info = quick_fail_mc.get_software_version(255, 255, 0)
                if "SpiNNaker" not in info.version_string:
                    raise SpiNNakerBootError(
                        "Remote host is not a SpiNNaker machine and so cannot "
                        "be booted. (Are you using a BMP IP/hostname?)")

                # Machine did not need booting
                return False
            except SCPError:
                # The machine is not responding to SCP so it needs booting.
                pass

        # Actually boot the machine
        boot_kwargs.setdefault("boot_port", self.boot_port)
        self.structs = boot.boot(self.initial_host, **boot_kwargs)
        assert len(self.structs) > 0

        # Wait for the machine to completely boot
        if check_booted:
            try:
                p2p_address = (255, 255)
                while p2p_address == (255, 255):
                    time.sleep(0.1)
                    p2p_address = self.get_software_version(
                        255, 255, 0).position
            except SCPError:
                # Machine did not respond
                raise SpiNNakerBootError(
                    "The remote machine could not be booted.")

        # The machine was sent boot commands
        return True

    @ContextMixin.use_contextual_arguments()
    def discover_connections(self, x=255, y=255):
        """Attempt to discover all available Ethernet connections to a machine.

        After calling this method, :py:class:`.MachineController` will attempt
        to communicate via the Ethernet connection on the same board as the
        destination chip for all commands.

        If called multiple times, existing connections will be retained in
        preference to new ones.

        .. note::
            The system must be booted for this command to succeed.

        .. note::
            Currently, only systems comprised of multiple Ethernet-connected
            SpiNN-5 boards are supported.

        Parameters
        ----------
        x : int
        y : int
            (Optional) The coordinates of the chip to initially use to query
            the system for the set of live chips.

        Returns
        -------
        int
            The number of new connections established.
        """
        working_chips = set(
            (x, y)
            for (x, y), route in iteritems(self.get_p2p_routing_table(x, y))
            if route != consts.P2PTableEntry.none)
        self._width = max(x for x, y in working_chips) + 1
        self._height = max(y for x, y in working_chips) + 1

        num_new_connections = 0

        for x, y in spinn5_eth_coords(self._width, self._height,
                                      *self.root_chip):
            if (x, y) in working_chips and (x, y) not in self.connections:
                # Discover the chip's IP address
                try:
                    ip = self.get_ip_address(x, y)
                except SCPError:
                    continue

                if ip is not None:
                    # Create a connection to the IP
                    self.connections[(x, y)] = \
                        SCPConnection(ip, self.scp_port,
                                      self.n_tries, self.timeout)

                    # Attempt to use the connection (and remove it if it
                    # doesn't work)
                    try:
                        self.get_software_version(x, y, 0)
                        num_new_connections += 1
                    except SCPError:
                        self.connections.pop((x, y)).close()

        return num_new_connections

    @ContextMixin.use_contextual_arguments()
    def application(self, app_id):
        """Update the context to use the given application ID and stop the
        application when done.

        For example::

            with cn.application(54):
                # All commands in this block will use app_id=54.
                # On leaving the block `cn.send_signal("stop", 54)` is
                # automatically called.
        """
        # Get a new context and add a method that will be called before the
        # context is removed from the stack.
        context = self(app_id=app_id)
        context.before_close(lambda: self.send_signal("stop"))
        return context

    @ContextMixin.use_contextual_arguments()
    def get_software_version(self, x=255, y=255, processor=0):
        """Get the software version for a given SpiNNaker core.

        Returns
        -------
        :py:class:`.CoreInfo`
            Information about the software running on a core.
        """
        sver = self._send_scp(x, y, processor, SCPCommands.sver)

        # Format the result
        # arg1 => p2p address, physical cpu, virtual cpu
        p2p = sver.arg1 >> 16
        p2p_address = (p2p >> 8, p2p & 0x00ff)
        pcpu = (sver.arg1 >> 8) & 0xff
        vcpu = sver.arg1 & 0xff

        # arg2 => version number (parsed separately) and buffer size
        buffer_size = (sver.arg2 & 0xffff)

        software_name, version, version_labels = \
            unpack_sver_response_version(sver)

        return CoreInfo(p2p_address, pcpu, vcpu, version, buffer_size,
                        sver.arg3, software_name, version_labels)

    @ContextMixin.use_contextual_arguments()
    def get_ip_address(self, x, y):
        """Get the IP address of a particular SpiNNaker chip's Ethernet link.

        Returns
        -------
        str or None
            The IPv4 address (as a string) of the chip's Ethernet link or None
            if the chip does not have an Ethernet connection or the link is
            currently down.
        """
        chip_info = self.get_chip_info(x=x, y=y)
        return chip_info.ip_address if chip_info.ethernet_up else None

    @ContextMixin.use_contextual_arguments()
    def write(self, address, data, x, y, p=0):
        """Write a bytestring to an address in memory.

        It is strongly encouraged to only read and write to blocks of memory
        allocated using :py:meth:`.sdram_alloc`. Additionally,
        :py:meth:`.sdram_alloc_as_filelike` can be used to safely wrap
        read/write access to memory with a file-like interface and prevent
        accidental access to areas outside the allocated block.

        Parameters
        ----------
        address : int
            The address at which to start writing the data. Addresses are given
            within the address space of a SpiNNaker core. See the SpiNNaker
            datasheet for more information.
        data : :py:class:`bytes`
            Data to write into memory. Writes are automatically broken into a
            sequence of SCP write commands.
        """
        # Call the SCPConnection to perform the write on our behalf
        connection = self._get_connection(x, y)
        return connection.write(self.scp_data_length, self.scp_window_size,
                                x, y, p, address, data)

    @ContextMixin.use_contextual_arguments()
    def read(self, address, length_bytes, x, y, p=0):
        """Read a bytestring from an address in memory.

        Parameters
        ----------
        address : int
            The address at which to start reading the data.
        length_bytes : int
            The number of bytes to read from memory. Large reads are
            transparently broken into multiple SCP read commands.

        Returns
        -------
        :py:class:`bytes`
            The data is read back from memory as a bytestring.
        """
        # Call the SCPConnection to perform the read on our behalf
        connection = self._get_connection(x, y)
        return connection.read(self.scp_data_length, self.scp_window_size,
                               x, y, p, address, length_bytes)

    @ContextMixin.use_contextual_arguments()
    def write_across_link(self, address, data, x, y, link):
        """Write a bytestring to an address in memory on a neigbouring chip.

        .. warning::

            This function is intended for low-level debug use only and is not
            optimised for performance nor intended for more general use.

        This method instructs a monitor processor to send 'POKE'
        nearest-neighbour packets to a neighbouring chip. These packets are
        handled directly by the SpiNNaker router in the neighbouring chip,
        potentially allowing advanced debug or recovery of a chip rendered
        otherwise unreachable.

        Parameters
        ----------
        address : int
            The address at which to start writing the data. Only addresses in
            the system-wide address map may be accessed. Addresses must be word
            aligned.
        data : :py:class:`bytes`
            Data to write into memory. Must be a whole number of words in
            length. Large writes are automatically broken into a sequence of
            SCP link-write commands.
        x : int
        y : int
            The coordinates of the chip from which the command will be sent,
            *not* the coordinates of the chip on which the write will be
            performed.
        link : :py:class:`rig.links.Links`
            The link down which the write should be sent.
        """
        if address % 4:
            raise ValueError("Addresses must be word-aligned.")
        if len(data) % 4:
            raise ValueError("Data must be a whole number of words.")

        length_bytes = len(data)
        cur_byte = 0

        # Write the requested data, one SCP packet worth at a time
        while length_bytes > 0:
            to_write = min(length_bytes, (self.scp_data_length & ~0b11))
            cur_data = data[cur_byte:cur_byte + to_write]
            self._send_scp(x, y, 0, SCPCommands.link_write,
                           arg1=address, arg2=to_write, arg3=int(link),
                           data=cur_data, expected_args=0)

            # Move to the next block to write
            address += to_write
            cur_byte += to_write
            length_bytes -= to_write

    @ContextMixin.use_contextual_arguments()
    def read_across_link(self, address, length_bytes, x, y, link):
        """Read a bytestring from an address in memory on a neigbouring chip.

        .. warning::

            This function is intended for low-level debug use only and is not
            optimised for performance nor intended for more general use.

        This method instructs a monitor processor to send 'PEEK'
        nearest-neighbour packets to a neighbouring chip. These packets are
        handled directly by the SpiNNaker router in the neighbouring chip,
        potentially allowing advanced debug or recovery of a chip rendered
        otherwise unreachable.

        Parameters
        ----------
        address : int
            The address at which to start reading the data. Only addresses in
            the system-wide address map may be accessed. Addresses must be word
            aligned.
        length_bytes : int
            The number of bytes to read from memory. Must be a multiple of four
            (i.e. a whole number of words). Large reads are transparently
            broken into multiple SCP link-read commands.
        x : int
        y : int
            The coordinates of the chip from which the command will be sent,
            *not* the coordinates of the chip on which the read will be
            performed.
        link : :py:class:`rig.links.Links`
            The link down which the read should be sent.

        Returns
        -------
        :py:class:`bytes`
            The data is read back from memory as a bytestring.
        """
        if address % 4:
            raise ValueError("Addresses must be word-aligned.")
        if length_bytes % 4:
            raise ValueError("Lengths must be multiples of words.")

        # Prepare the buffer to receive the incoming data
        data = bytearray(length_bytes)
        mem = memoryview(data)

        # Read the requested data, one SCP packet worth at a time
        while length_bytes > 0:
            to_read = min(length_bytes, (self.scp_data_length & ~0b11))
            response = self._send_scp(x, y, 0, SCPCommands.link_read,
                                      arg1=address,
                                      arg2=to_read,
                                      arg3=int(link),
                                      expected_args=0)

            # Accumulate the incoming data and advance the memoryview through
            # the buffer.
            mem[:to_read] = response.data
            mem = mem[to_read:]

            # Move to the next block to read
            address += to_read
            length_bytes -= to_read

        return bytes(data)

    def _get_struct_field_and_address(self, struct_name, field_name):
        field = self.structs[six.b(struct_name)][six.b(field_name)]
        address = self.structs[six.b(struct_name)].base + field.offset
        # NOTE Python 2 and 3 fix
        pack_chars = b"<" + (field.length * field.pack_chars)
        return field, address, pack_chars

    @ContextMixin.use_contextual_arguments()
    def read_struct_field(self, struct_name, field_name, x, y, p=0):
        """Read the value out of a struct maintained by SARK.

        This method is particularly useful for reading fields from the ``sv``
        struct which, for example, holds information about system status. See
        ``sark.h`` for details.

        Parameters
        ----------
        struct_name : string
            Name of the struct to read from, e.g., `"sv"`
        field_name : string
            Name of the field to read, e.g., `"eth_addr"`

        Returns
        -------
        value
            The value returned is unpacked given the struct specification.

            Currently arrays are returned as tuples, e.g.::

                # Returns a 20-tuple.
                cn.read_struct_field("sv", "status_map")

                # Fails
                cn.read_struct_field("sv", "status_map[1]")
        """
        # Look up the struct and field
        field, address, pack_chars = \
            self._get_struct_field_and_address(struct_name, field_name)
        length = struct.calcsize(pack_chars)

        # Perform the read
        data = self.read(address, length, x, y, p)

        # Unpack the data
        unpacked = struct.unpack(pack_chars, data)

        if field.length == 1:
            return unpacked[0]
        else:
            return unpacked

    @ContextMixin.use_contextual_arguments()
    def write_struct_field(self, struct_name, field_name, values, x, y, p=0):
        """Write a value into a struct.

        This method is particularly useful for writing values into the ``sv``
        struct which contains some configuration data.  See ``sark.h`` for
        details.

        Parameters
        ----------
        struct_name : string
            Name of the struct to write to, e.g., `"sv"`
        field_name : string
            Name of the field to write, e.g., `"random"`
        values :
            Value(s) to be written into the field.

        .. warning::
            Fields which are arrays must currently be written in their
            entirety.
        """
        # Look up the struct and field
        field, address, pack_chars = \
            self._get_struct_field_and_address(struct_name, field_name)

        if field.length != 1:
            assert len(values) == field.length
            data = struct.pack(pack_chars, *values)
        else:
            data = struct.pack(pack_chars, values)

        # Perform the write
        self.write(address, data, x, y, p)

    def _get_vcpu_field_and_address(self, field_name, x, y, p):
        """Get the field and address for a VCPU struct field."""
        vcpu_struct = self.structs[b"vcpu"]
        field = vcpu_struct[six.b(field_name)]
        address = (self.read_struct_field("sv", "vcpu_base", x, y) +
                   vcpu_struct.size * p) + field.offset
        pack_chars = b"<" + field.pack_chars
        return field, address, pack_chars

    @ContextMixin.use_contextual_arguments()
    def read_vcpu_struct_field(self, field_name, x, y, p):
        """Read a value out of the VCPU struct for a specific core.

        Similar to :py:meth:`.read_struct_field` except this method accesses
        the individual VCPU struct for to each core and contains application
        runtime status.

        Parameters
        ----------
        field_name : string
            Name of the field to read from the struct (e.g. `"cpu_state"`)

        Returns
        -------
        value
            A value of the type contained in the specified struct field.
        """
        # Get the base address of the VCPU struct for this chip, then advance
        # to get the correct VCPU struct for the requested core.
        field, address, pack_chars = \
            self._get_vcpu_field_and_address(field_name, x, y, p)

        # Perform the read
        length = struct.calcsize(pack_chars)
        data = self.read(address, length, x, y)

        # Unpack and return
        unpacked = struct.unpack(pack_chars, data)

        if field.length == 1:
            return unpacked[0]
        else:
            # If the field is a string then truncate it and return
            if b"s" in pack_chars:
                return unpacked[0].strip(b"\x00").decode("utf-8")

            # Otherwise just return. (Note: at the time of writing, no fields
            # in the VCPU struct are of this form.)
            return unpacked  # pragma: no cover

    @ContextMixin.use_contextual_arguments()
    def write_vcpu_struct_field(self, field_name, value, x, y, p):
        """Write a value to the VCPU struct for a specific core.

        Parameters
        ----------
        field_name : string
            Name of the field to write (e.g. `"user0"`)
        value :
            Value to write to this field.
        """
        field, address, pack_chars = \
            self._get_vcpu_field_and_address(field_name, x, y, p)

        # Pack the data
        if b"s" in pack_chars:
            data = struct.pack(pack_chars, value.encode('utf-8'))
        elif field.length == 1:
            data = struct.pack(pack_chars, value)
        else:
            # NOTE: At the time of writing no VCPU struct fields are of this
            # form.
            data = struct.pack(pack_chars, *value)  # pragma: no cover

        # Perform the write
        self.write(address, data, x, y)

    @ContextMixin.use_contextual_arguments()
    def get_processor_status(self, p, x, y):
        """Get the status of a given core and the application executing on it.

        Returns
        -------
        :py:class:`.ProcessorStatus`
            Representation of the current state of the processor.
        """
        # Get the VCPU base
        address = (self.read_struct_field("sv", "vcpu_base", x, y) +
                   self.structs[b"vcpu"].size * p)

        # Get the VCPU data
        data = self.read(address, self.structs[b"vcpu"].size, x, y)

        # Build the kwargs that describe the current state
        state = {
            name.decode('utf-8'): struct.unpack(
                f.pack_chars,
                data[f.offset:f.offset+struct.calcsize(f.pack_chars)]
            )[0] for (name, f) in iteritems(self.structs[b"vcpu"].fields)
        }
        state["registers"] = [state.pop("r{}".format(i)) for i in range(8)]
        state["user_vars"] = [state.pop("user{}".format(i)) for i in range(4)]
        state["app_name"] = state["app_name"].strip(b'\x00').decode('utf-8')
        state["cpu_state"] = consts.AppState(state["cpu_state"])
        state["rt_code"] = consts.RuntimeException(state["rt_code"])

        sw_ver = state.pop("sw_ver")
        state["version"] = ((sw_ver >> 16) & 0xFF,
                            (sw_ver >> 8) & 0xFF,
                            (sw_ver >> 0) & 0xFF)

        for newname, oldname in [("iobuf_address", "iobuf"),
                                 ("program_state_register", "psr"),
                                 ("stack_pointer", "sp"),
                                 ("link_register", "lr"), ]:
            state[newname] = state.pop(oldname)
        state.pop("__PAD")
        return ProcessorStatus(**state)

    @ContextMixin.use_contextual_arguments()
    def get_iobuf(self, p, x, y):
        """Read the messages ``io_printf``'d into the ``IOBUF`` buffer on a
        specified core.

        See also: :py:meth:`.get_iobuf_bytes` which returns the undecoded raw
        bytes in the ``IOBUF``. Useful if the IOBUF contains non-text or
        non-UTF-8 encoded text.

        Returns
        -------
        str
            The string in the ``IOBUF``, decoded from UTF-8.
        """
        return self.get_iobuf_bytes(p, x, y).decode("utf-8")

    @ContextMixin.use_contextual_arguments()
    def get_iobuf_bytes(self, p, x, y):
        """Read raw bytes ``io_printf``'d into the ``IOBUF`` buffer on a
        specified core.

        This may be useful when the data contained in the ``IOBUF`` is not
        UTF-8 encoded text.

        See also: :py:meth:`.get_iobuf` which returns a decoded string rather
        than raw bytes.

        Returns
        -------
        bytes
            The raw, undecoded string data in the buffer.
        """
        # The IOBUF data is stored in a linked-list of blocks of memory in
        # SDRAM. The size of each block is given in SV
        iobuf_size = self.read_struct_field("sv", "iobuf_size", x, y)

        # The first block in the list is given in the core's VCPU field
        address = self.read_vcpu_struct_field("iobuf", x, y, p)

        iobuf = b""

        while address:
            # The IOBUF data is proceeded by a header which gives the next
            # address and also the length of the string in the current buffer.
            iobuf_data = self.read(address, iobuf_size + 16, x, y)
            address, time, ms, length = struct.unpack("<4I", iobuf_data[:16])
            iobuf += iobuf_data[16:16 + length]

        return iobuf

    @ContextMixin.use_contextual_arguments()
    def get_router_diagnostics(self, x, y):
        """Get the values of the router diagnostic counters.

        Returns
        -------
        :py:class:`~.RouterDiagnostics`
            Description of the state of the counters.
        """
        # Read the block of memory
        data = self.read(0xe1000300, 64, x=x, y=y)

        # Convert to 16 ints, then process that as the appropriate tuple type
        return RouterDiagnostics(*struct.unpack("<16I", data))

    @ContextMixin.use_contextual_arguments()
    def iptag_set(self, iptag, addr, port, x, y):
        """Set the value of an IPTag.

        Forward SDP packets with the specified IP tag sent by a SpiNNaker
        application to a given external IP address.

        A :ref:`tutorial example <scp-and-sdp-tutorial>` of the use of IP Tags
        to send and receive SDP packets to and from applications is also
        available.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to set
        addr : string
            IP address or hostname that the IPTag should point at.
        port : int
            UDP port that the IPTag should direct packets to.
        """
        # Format the IP address
        ip_addr = struct.pack('!4B',
                              *map(int, socket.gethostbyname(addr).split('.')))
        self._send_scp(x, y, 0, SCPCommands.iptag,
                       int(consts.IPTagCommands.set) << 16 | iptag,
                       port, struct.unpack('<I', ip_addr)[0])

    @ContextMixin.use_contextual_arguments()
    def iptag_get(self, iptag, x, y):
        """Get the value of an IPTag.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to get

        Returns
        -------
        :py:class:`.IPTag`
            The IPTag returned from SpiNNaker.
        """
        ack = self._send_scp(x, y, 0, SCPCommands.iptag,
                             int(consts.IPTagCommands.get) << 16 | iptag, 1,
                             expected_args=0)
        return IPTag.from_bytestring(ack.data)

    @ContextMixin.use_contextual_arguments()
    def iptag_clear(self, iptag, x, y):
        """Clear an IPTag.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to clear.
        """
        self._send_scp(x, y, 0, SCPCommands.iptag,
                       int(consts.IPTagCommands.clear) << 16 | iptag)

    @ContextMixin.use_contextual_arguments()
    def set_led(self, led, action=None, x=Required, y=Required):
        """Set or toggle the state of an LED.

        .. note::
            By default, SARK takes control of LED 0 and so changes to this LED
            will not typically last long enough to be useful.

        Parameters
        ----------
        led : int or iterable
            Number of the LED or an iterable of LEDs to set the state of (0-3)
        action : bool or None
            State to set the LED to. True for on, False for off, None to
            toggle (default).
        """
        if isinstance(led, int):
            leds = [led]
        else:
            leds = led
        arg1 = sum(LEDAction.from_bool(action) << (led * 2) for led in leds)
        self._send_scp(x, y, 0, SCPCommands.led, arg1=arg1, expected_args=0)

    @ContextMixin.use_contextual_arguments()
    def fill(self, address, data, size, x, y, p):
        """Fill a region of memory with the specified byte.

        Parameters
        ----------
        data : int
            Data with which to fill memory. If `address` and `size` are word
            aligned then `data` is assumed to be a word; otherwise it is
            assumed to be a byte.

        Notes
        -----
        If the address and size are word aligned then a fast fill method will
        be used, otherwise a much slower write will be incurred.
        """
        if size % 4 or address % 4:
            # If neither the size nor the address are word aligned we have to
            # use `write` as `sark_word_set` can only work with words.
            # Convert the data into a string and then write:
            data = struct.pack('<B', data) * size
            self.write(address, data, x, y, p)
        else:
            # We can perform a fill, this will call `sark_word_set` internally.
            self._send_scp(x, y, p, SCPCommands.fill, address, data, size)

    @ContextMixin.use_contextual_arguments()
    def sdram_alloc(self, size, tag=0, x=Required, y=Required,
                    app_id=Required, clear=False):
        """Allocate a region of SDRAM for an application.

        Requests SARK to allocate a block of SDRAM for an application and
        raises a :py:exc:`.SpiNNakerMemoryError` on failure. This allocation
        will be freed when the application is stopped.

        Parameters
        ----------
        size : int
            Number of bytes to attempt to allocate in SDRAM.
        tag : int
            8-bit tag that can be looked up by a SpiNNaker application to
            discover the address of the allocated block. The tag must be unique
            for this ``app_id`` on this chip. Attempting to allocate two blocks
            on the same chip and for the same ``app_id`` will fail. If ``0``
            (the default) then no tag is applied.

            For example, if some SDRAM is allocated with ``tag=12``, a
            SpiNNaker application can later discover the address using::

                void *allocated_data = sark_tag_ptr(12, 0);

            A common convention is to allocate one block of SDRAM per
            application core and give each allocation the associated core
            number as its tag. This way the underlying SpiNNaker applications
            can simply call::

                void *allocated_data = sark_tag_ptr(sark_core_id(), 0);

        clear : bool
            If True the requested memory will be filled with zeros before the
            pointer is returned.  If False (the default) the memory will be
            left as-is.

        Returns
        -------
        int
            Address of the start of the region.

            The allocated SDRAM remains valid until either the 'stop' signal is
            sent to the application ID associated with the allocation or
            :py:meth:`.sdram_free` is called on the address returned.

        Raises
        ------
        rig.machine_control.machine_controller.SpiNNakerMemoryError
            If the memory cannot be allocated, the tag is already taken or it
            is invalid.
        """
        assert 0 <= tag < 256

        # Construct arg1 (app_id << 8) | op code
        arg1 = app_id << 8 | consts.AllocOperations.alloc_sdram

        # Send the packet and retrieve the address
        rv = self._send_scp(x, y, 0, SCPCommands.alloc_free, arg1, size, tag)
        if rv.arg1 == 0:
            # Allocation failed
            raise SpiNNakerMemoryError(size, x, y, tag)

        # Get the address
        address = rv.arg1

        if clear:
            # Clear the memory if so desired
            self.fill(address, 0, size, x, y, 0)

        return address

    @ContextMixin.use_contextual_arguments()
    def sdram_alloc_as_filelike(self, size, tag=0, x=Required, y=Required,
                                app_id=Required, clear=False):
        """Like :py:meth:`.sdram_alloc` but returns a :py:class:`file-like
        object <.MemoryIO>` which allows safe reading and writing to the block
        that is allocated.

        Returns
        -------
        :py:class:`.MemoryIO`
            File-like object which allows accessing the newly allocated region
            of memory. For example::

                >>> # Read, write and seek through the allocated memory just
                >>> # like a file
                >>> mem = mc.sdram_alloc_as_filelike(12)  # doctest: +SKIP
                >>> mem.write(b"Hello, world")            # doctest: +SKIP
                12
                >>> mem.seek(0)                           # doctest: +SKIP
                >>> mem.read(5)                           # doctest: +SKIP
                b"Hello"
                >>> mem.read(7)                           # doctest: +SKIP
                b", world"

                >>> # Reads and writes are truncated to the allocated region,
                >>> # preventing accidental clobbering/access of memory.
                >>> mem.seek(0)                           # doctest: +SKIP
                >>> mem.write(b"How are you today?")      # doctest: +SKIP
                12
                >>> mem.seek(0)                           # doctest: +SKIP
                >>> mem.read(100)                         # doctest: +SKIP
                b"How are you "

            See the :py:class:`.MemoryIO` class for details of other features
            of these file-like views of SpiNNaker's memory.

        Raises
        ------
        rig.machine_control.machine_controller.SpiNNakerMemoryError
            If the memory cannot be allocated, or the tag is already taken or
            invalid.
        """
        # Perform the malloc
        start_address = self.sdram_alloc(size, tag, x, y, app_id, clear)
        return MemoryIO(self, x, y, start_address, start_address + size)

    @ContextMixin.use_contextual_arguments()
    def sdram_free(self, ptr, x=Required, y=Required):
        """Free an allocated block of memory in SDRAM.

        .. note::

            All unfreed SDRAM allocations associated with an application are
            automatically freed when the 'stop' signal is sent (e.g. after
            leaving a :py:meth:`.application` block). As such, this method is
            only useful when specific blocks are to be freed while retaining
            others.

        Parameters
        ----------
        ptr : int
            Address of the block of memory to free.
        """
        self._send_scp(x, y, 0, SCPCommands.alloc_free,
                       consts.AllocOperations.free_sdram_by_ptr, ptr)

    def _get_next_nn_id(self):
        """Get the next nearest neighbour ID."""
        self._nn_id = self._nn_id + 1 if self._nn_id < 126 else 1
        return self._nn_id * 2

    def _send_ffs(self, pid, n_blocks, fr):
        """Send a flood-fill start packet.

        The cores and regions that the application should be loaded to will be
        specified by a stream of flood-fill core select packets (FFCS).
        """
        sfr = fr | (1 << 31)
        self._send_scp(
            255, 255, 0, SCPCommands.nearest_neighbour_packet,
            (NNCommands.flood_fill_start << 24) | (pid << 16) |
            (n_blocks << 8), 0x0, sfr
        )

    def _send_ffcs(self, region, core_mask, fr):
        """Send a flood-fill core select packet.

        This packet was added in a patched SC&MP 1.34*. Each packet includes a
        region and a core mask; every core that is in the region ORs the core
        mask with a mask it stores locally. On receiving a flood-fill end (FFE)
        packet the application is loaded to the cores specified by this
        composed core mask.

        FFCS packets should be sent in ascending order of
        `(region << 18) | core`.

        * See https://bitbucket.org/mundya/scamp/branch/new-ff2
        """
        arg1 = (NNCommands.flood_fill_core_select << 24) | core_mask
        arg2 = region
        self._send_scp(255, 255, 0, SCPCommands.nearest_neighbour_packet,
                       arg1, arg2, fr)

    def _send_ffd(self, pid, aplx_data, address):
        """Send flood-fill data packets."""
        block = 0
        pos = 0
        aplx_size = len(aplx_data)

        while pos < aplx_size:
            # Get the next block of data, send and progress the block
            # counter and the address
            data = aplx_data[pos:pos + self.scp_data_length]
            data_size = len(data)
            size = data_size // 4 - 1

            arg1 = (NNConstants.forward << 24 | NNConstants.retry << 16 | pid)
            arg2 = (block << 16) | (size << 8)
            self._send_scp(255, 255, 0, SCPCommands.flood_fill_data,
                           arg1, arg2, address, data)

            # Increment the address and the block counter
            block += 1
            address += data_size
            pos += data_size

    def _send_ffe(self, pid, app_id, app_flags, fr):
        """Send a flood-fill end packet.

        The cores and regions that the application should be loaded to will
        have been specified by a stream of flood-fill core select packets
        (FFCS).
        """
        arg1 = (NNCommands.flood_fill_end << 24) | pid
        arg2 = (app_id << 24) | (app_flags << 18)
        self._send_scp(255, 255, 0, SCPCommands.nearest_neighbour_packet,
                       arg1, arg2, fr)

    @ContextMixin.use_contextual_arguments(app_id=Required, wait=True)
    def flood_fill_aplx(self, *args, **kwargs):
        """Unreliably flood-fill APLX to a set of application cores.

        .. note::

            Most users should use the :py:meth:`.load_application` wrapper
            around this method which guarantees successful loading.

        This method can be called in either of the following ways::

            flood_fill_aplx("/path/to/app.aplx", {(x, y): {core, ...}, ...})
            flood_fill_aplx({"/path/to/app.aplx": {(x, y): {core, ...}, ...},
                             ...})

        Note that the latter format is the same format produced by
        :py:func:`~rig.place_and_route.util.build_application_map`.

        .. warning::

            The loading process is likely, but not guaranteed, to succeed.
            This is because the flood-fill packets used during loading are not
            guaranteed to arrive. The effect is that some chips may not receive
            the complete application binary and will silently ignore the
            application loading request.

            As a result, the user is responsible for checking that each core
            was successfully loaded with the correct binary. At present, the
            two recommended approaches to this are:

            * If the ``wait`` argument is given then the user should check that
              the correct number of application binaries reach the initial
              barrier (i.e., the ``wait`` state). If the number does not match
              the expected number of loaded cores the next approach must be
              used:
            * The user can check the process list of each chip to ensure the
              application was loaded into the correct set of cores. See
              :py:meth:`.read_vcpu_struct_field`.

        Parameters
        ----------
        app_id : int
        wait : bool (Default: True)
            Should the application await the AppSignal.start signal after it
            has been loaded?
        """
        # Coerce the arguments into a single form.  If there are two arguments
        # then assume that we have filename and a map of chips and cores;
        # otherwise there should be ONE argument which is of the form of the
        # return value of `build_application_map`.
        application_map = {}
        if len(args) == 1:
            application_map = args[0]
        elif len(args) == 2:
            application_map = {args[0]: args[1]}
        else:
            raise TypeError(
                "flood_fill_aplx: accepts either 1 or 2 positional arguments: "
                "a map of filenames to targets OR a single filename and its"
                "targets"
            )

        # Get the application ID, the context system will guarantee that this
        # is available
        app_id = kwargs.pop("app_id")

        flags = 0x0000
        if kwargs.pop("wait"):
            flags |= AppFlags.wait

        # The forward and retry parameters
        fr = NNConstants.forward << 8 | NNConstants.retry

        # Load each APLX in turn
        for (aplx, targets) in iteritems(application_map):
            # Determine the minimum number of flood-fills that are necessary to
            # load the APLX. The regions and cores should be sorted into
            # ascending order, `compress_flood_fill_regions` ensures this is
            # done.
            fills = regions.compress_flood_fill_regions(targets)

            # Load the APLX data
            with open(aplx, "rb") as f:
                aplx_data = f.read()
            n_blocks = ((len(aplx_data) + self.scp_data_length - 1) //
                        self.scp_data_length)

            # Start the flood fill for this application
            # Get an index for the nearest neighbour operation
            pid = self._get_next_nn_id()

            # Send the flood-fill start packet
            self._send_ffs(pid, n_blocks, fr)

            # Send the core select packets
            for (region, cores) in fills:
                self._send_ffcs(region, cores, fr)

            # Send the data
            base_address = self.read_struct_field(
                "sv", "sdram_sys", 255, 255)
            self._send_ffd(pid, aplx_data, base_address)

            # Send the flood-fill END packet
            self._send_ffe(pid, app_id, flags, fr)

    @ContextMixin.use_contextual_arguments(app_id=Required, n_tries=2,
                                           wait=False,
                                           app_start_delay=0.1)
    def load_application(self, *args, **kwargs):
        """Load an application to a set of application cores.

        This method guarantees that once it returns, all required cores will
        have been loaded. If this is not possible after a small number of
        attempts, a :py:exc:`.SpiNNakerLoadingError` will be raised.

        This method can be called in either of the following ways::

            load_application("/path/to/app.aplx", {(x, y): {core, ...}, ...})
            load_application({"/path/to/app.aplx": {(x, y): {core, ...}, ...},
                              ...})

        Note that the latter format is the same format produced by
        :py:func:`~rig.place_and_route.util.build_application_map`.

        Parameters
        ----------
        app_id : int
        wait : bool
            Leave the application in a wait state after successfully loading
            it.
        n_tries : int
            Number attempts to make to load the application.
        app_start_delay : float
            Time to pause (in seconds) after loading to ensure that the
            application successfully reaches the wait state before checking for
            success.
        use_count : bool
            If True (the default) then the targets dictionary will be assumed
            to represent _all_ the cores that will be loaded and a faster
            method to determine whether all applications have been loaded
            correctly will be used. If False a fallback method will be used.

        Raises
        ------
        rig.machine_control.machine_controller.SpiNNakerLoadingError
            This exception is raised after some cores failed to load after
            ``n_tries`` attempts.
        """
        # Get keyword arguments
        app_id = kwargs.pop("app_id")
        wait = kwargs.pop("wait")
        n_tries = kwargs.pop("n_tries")
        app_start_delay = kwargs.pop("app_start_delay")
        use_count = kwargs.pop("use_count", True)

        # Coerce the arguments into a single form.  If there are two arguments
        # then assume that we have filename and a map of chips and cores;
        # otherwise there should be ONE argument which is of the form of the
        # return value of `build_application_map`.
        application_map = {}
        if len(args) == 1:
            application_map = args[0]
        elif len(args) == 2:
            application_map = {args[0]: args[1]}
        else:
            raise TypeError(
                "load_application: accepts either 1 or 2 positional arguments:"
                "a map of filenames to targets OR a single filename and its"
                "targets"
            )

        # Count the number of cores being loaded
        core_count = sum(
            len(cores) for ts in six.itervalues(application_map) for
            cores in six.itervalues(ts)
        )

        # Mark all targets as unloaded
        unloaded = application_map

        # Try to load the applications, then determine which are unloaded
        tries = 0
        while unloaded != {} and tries <= n_tries:
            tries += 1

            # Load all unloaded applications, then pause to ensure they reach
            # the wait state
            self.flood_fill_aplx(unloaded, app_id=app_id, wait=True)
            time.sleep(app_start_delay)

            # If running in "fast" mode then check that the correct number of
            # cores are in the "wait" state, if so then break out of this loop.
            if (use_count and
                    core_count == self.count_cores_in_state("wait", app_id)):
                unloaded = {}
                continue

            # Query each target in turn to determine if it is loaded or
            # otherwise.  If it is loaded (in the wait state) then remove it
            # from the unloaded list.
            new_unloadeds = dict()
            for app_name, targets in iteritems(unloaded):
                unloaded_targets = {}
                for (x, y), cores in iteritems(targets):
                    unloaded_cores = set()
                    for p in cores:
                        # Read the struct value vcpu->cpu_state, if it is
                        # anything BUT wait then we mark this core as unloaded.
                        state = consts.AppState(
                            self.read_vcpu_struct_field("cpu_state", x, y, p)
                        )
                        if state is not consts.AppState.wait:
                            unloaded_cores.add(p)

                    if len(unloaded_cores) > 0:
                        unloaded_targets[(x, y)] = unloaded_cores
                if len(unloaded_targets) > 0:
                    new_unloadeds[app_name] = unloaded_targets
            unloaded = new_unloadeds

        # If there are still unloaded cores then we bail
        if unloaded != {}:
            raise SpiNNakerLoadingError(unloaded)

        # If not waiting then send the start signal
        if not wait:
            self.send_signal("start", app_id)

    @ContextMixin.use_contextual_arguments()
    def send_signal(self, signal, app_id):
        """Transmit a signal to applications.

        .. warning::
            In current implementations of SARK, signals are highly likely to
            arrive but this is not guaranteed (especially when the system's
            network is heavily utilised). Users should treat this mechanism
            with caution. Future versions of SARK may resolve this issue.

        Parameters
        ----------
        signal : string or :py:class:`~rig.machine_control.consts.AppSignal`
            Signal to transmit. This may be either an entry of the
            :py:class:`~rig.machine_control.consts.AppSignal` enum or, for
            convenience, the name of a signal (defined in
            :py:class:`~rig.machine_control.consts.AppSignal`) as a string.
        """
        if isinstance(signal, str):
            try:
                signal = getattr(consts.AppSignal, signal)
            except AttributeError:
                # The signal name is not present in consts.AppSignal! The next
                # test will throw an appropriate exception since no string can
                # be "in" an IntEnum.
                pass
        if signal not in consts.AppSignal:
            raise ValueError(
                "send_signal: Cannot transmit signal of type {}".format(
                    repr(signal)))

        # Construct the packet for transmission
        arg1 = consts.signal_types[signal]
        arg2 = (signal << 16) | 0xff00 | app_id
        arg3 = 0x0000ffff  # Meaning "transmit to all"
        self._send_scp(255, 255, 0, SCPCommands.signal, arg1, arg2, arg3)

    @ContextMixin.use_contextual_arguments()
    def count_cores_in_state(self, state, app_id):
        """Count the number of cores in a given state.

        .. warning::
            In current implementations of SARK, signals (which are used to
            determine the state of cores) are highly likely to arrive but this
            is not guaranteed (especially when the system's network is heavily
            utilised). Users should treat this mechanism with caution. Future
            versions of SARK may resolve this issue.

        Parameters
        ----------
        state : string or :py:class:`~rig.machine_control.consts.AppState` or
                iterable
            Count the number of cores currently in this state. This may be
            either an entry of the
            :py:class:`~rig.machine_control.consts.AppState` enum or, for
            convenience, the name of a state (defined in
            :py:class:`~rig.machine_control.consts.AppState`) as a string or
            an iterable of these, in which case the total count will be
            returned.
        """
        if (isinstance(state, collections.Iterable) and
                not isinstance(state, str)):
            # If the state is iterable then call for each state and return the
            # sum.
            return sum(self.count_cores_in_state(s, app_id) for s in state)

        if isinstance(state, str):
            try:
                state = getattr(consts.AppState, state)
            except AttributeError:
                # The state name is not present in consts.AppSignal! The next
                # test will throw an appropriate exception since no string can
                # be "in" an IntEnum.
                pass
        if state not in consts.AppState:
            raise ValueError(
                "count_cores_in_state: Unknown state {}".format(
                    repr(state)))

        # TODO Determine a way to nicely express a way to use the region data
        # stored in arg3.
        region = 0x0000ffff  # Largest possible machine, level 0
        level = (region >> 16) & 0x3
        mask = region & 0x0000ffff

        # Construct the packet
        arg1 = consts.diagnostic_signal_types[consts.AppDiagnosticSignal.count]
        arg2 = ((level << 26) | (1 << 22) |
                (consts.AppDiagnosticSignal.count << 20) | (state << 16) |
                (0xff << 8) | app_id)  # App mask for 1 app_id = 0xff
        arg3 = mask

        # Transmit and return the count
        return self._send_scp(
            255, 255, 0, SCPCommands.signal, arg1, arg2, arg3).arg1

    @ContextMixin.use_contextual_arguments()
    def wait_for_cores_to_reach_state(self, state, count, app_id,
                                      poll_interval=0.1, timeout=None):
        """Block until the specified number of cores reach the specified state.

        This is a simple utility-wrapper around the
        :py:meth:`.count_cores_in_state` method which polls the machine until
        (at least) the supplied number of cores has reached the specified
        state.

        .. warning::
            In current implementations of SARK, signals (which are used to
            determine the state of cores) are highly likely to arrive but this
            is not guaranteed (especially when the system's network is heavily
            utilised). As a result, in uncommon-but-possible circumstances,
            this function may never exit. Users should treat this function with
            caution. Future versions of SARK may resolve this issue.

        Parameters
        ----------
        state : string or :py:class:`~rig.machine_control.consts.AppState`
            The state to wait for cores to enter. This may be
            either an entry of the
            :py:class:`~rig.machine_control.consts.AppState` enum or, for
            convenience, the name of a state (defined in
            :py:class:`~rig.machine_control.consts.AppState`) as a string.
        count : int
            The (minimum) number of cores reach the specified state before this
            method terminates.
        poll_interval : float
            Number of seconds between state counting requests sent to the
            machine.
        timeout : float or Null
            Maximum number of seconds which may elapse before giving up. If
            None, keep trying forever.

        Returns
        -------
        int
            The number of cores in the given state (which will be less than the
            number required if the method timed out).
        """
        if timeout is not None:
            timeout_time = time.time() + timeout

        while True:
            cur_count = self.count_cores_in_state(state, app_id)
            if cur_count >= count:
                break

            # Stop if timeout elapsed
            if timeout is not None and time.time() > timeout_time:
                break

            # Pause before retrying
            time.sleep(poll_interval)

        return cur_count

    @ContextMixin.use_contextual_arguments()
    def load_routing_tables(self, routing_tables, app_id):
        """Allocate space for an load multicast routing tables.

        The routing table entries will be removed automatically when the
        associated application is stopped.

        Parameters
        ----------
        routing_tables : {(x, y): \
                          [:py:class:`~rig.routing_table.RoutingTableEntry`\
                           (...), ...], ...}
            Map of chip co-ordinates to routing table entries, as produced, for
            example by
            :py:func:`~rig.routing_table.routing_tree_to_tables` and
            :py:func:`~rig.routing_table.minimise_tables`.

        Raises
        ------
        rig.machine_control.machine_controller.SpiNNakerRouterError
            If it is not possible to allocate sufficient routing table entries.
        """
        for (x, y), table in iteritems(routing_tables):
            self.load_routing_table_entries(table, x=x, y=y, app_id=app_id)

    @ContextMixin.use_contextual_arguments()
    def load_routing_table_entries(self, entries, x, y, app_id):
        """Allocate space for and load multicast routing table entries into the
        router of a SpiNNaker chip.

        .. note::
            This method only loads routing table entries for a single chip.
            Most users should use :py:meth:`.load_routing_tables` which loads
            routing tables to multiple chips.

        Parameters
        ----------
        entries : [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
            List of :py:class:`rig.routing_table.RoutingTableEntry`\ s.

        Raises
        ------
        rig.machine_control.machine_controller.SpiNNakerRouterError
            If it is not possible to allocate sufficient routing table entries.
        """
        count = len(entries)

        # Try to allocate room for the entries
        rv = self._send_scp(
            x, y, 0, SCPCommands.alloc_free,
            (app_id << 8) | consts.AllocOperations.alloc_rtr, count
        )
        rtr_base = rv.arg1  # Index of the first allocated entry, 0 if failed

        if rtr_base == 0:
            raise SpiNNakerRouterError(count, x, y)

        # Determine where to write into memory
        buf = self.read_struct_field("sv", "sdram_sys", x, y)

        # Build the data to write in, then perform the write
        data = bytearray(16 * len(entries))
        for i, entry in enumerate(entries):
            # Build the route as a 32-bit value
            route = 0x00000000
            for r in entry.route:
                route |= 1 << r

            struct.pack_into(consts.RTE_PACK_STRING, data, i*16,
                             i, 0, route, entry.key, entry.mask)
        self.write(buf, data, x, y)

        # Perform the load of the data into the router
        self._send_scp(
            x, y, 0, SCPCommands.router,
            (count << 16) | (app_id << 8) | consts.RouterOperations.load,
            buf, rtr_base
        )

    @ContextMixin.use_contextual_arguments()
    def get_routing_table_entries(self, x, y):
        """Dump the multicast routing table of a given chip.

        Returns
        -------
        [(:py:class:`~rig.routing_table.RoutingTableEntry`, app_id, core) \
          or None, ...]
            Ordered list of routing table entries with app_ids and
            core numbers.
        """
        # Determine where to read from, perform the read
        rtr_addr = self.read_struct_field("sv", "rtr_copy", x, y)
        read_size = struct.calcsize(consts.RTE_PACK_STRING)
        rtr_data = self.read(rtr_addr, consts.RTR_ENTRIES * read_size, x, y)

        # Read each routing table entry in turn
        table = list()
        while len(rtr_data) > 0:
            entry, rtr_data = rtr_data[:read_size], rtr_data[read_size:]
            table.append(unpack_routing_table_entry(entry))
        return table

    @ContextMixin.use_contextual_arguments()
    def clear_routing_table_entries(self, x, y, app_id):
        """Clear the routing table entries associated with a given application.
        """
        # Construct the arguments
        arg1 = (app_id << 8) | consts.AllocOperations.free_rtr_by_app
        self._send_scp(x, y, 0, SCPCommands.alloc_free, arg1, 0x1)

    @ContextMixin.use_contextual_arguments()
    def get_p2p_routing_table(self, x, y):
        """Dump the contents of a chip's P2P routing table.

        This method can be indirectly used to get a list of functioning chips.

        .. note::
            This method only returns the entries for chips within the bounds of
            the system. E.g. if booted with 8x8 only entries for these 8x8
            chips will be returned.

        Returns
        -------
        {(x, y): :py:class:`~rig.machine_control.consts.P2PTableEntry`, ...}
        """
        table = {}

        # Get the dimensions of the system
        p2p_dims = self.read_struct_field("sv", "p2p_dims", x, y)
        width = (p2p_dims >> 8) & 0xFF
        height = (p2p_dims >> 0) & 0xFF

        # Read out the P2P table data, one column at a time (note that eight
        # entries are packed into each 32-bit word)
        col_words = (((height + 7) // 8) * 4)
        for col in range(width):
            # Read the entries for this row
            raw_table_col = self.read(
                consts.SPINNAKER_RTR_P2P + (((256 * col) // 8) * 4),
                col_words,
                x, y
            )

            row = 0
            while row < height:
                raw_word, raw_table_col = raw_table_col[:4], raw_table_col[4:]
                word, = struct.unpack("<I", raw_word)
                for entry in range(min(8, height - row)):
                    table[(col, row)] = \
                        consts.P2PTableEntry((word >> (3*entry)) & 0b111)
                    row += 1

        return table

    @ContextMixin.use_contextual_arguments()
    def get_chip_info(self, x, y):
        """Get general information about the resources available on a chip.

        Returns
        -------
        :py:class:`.ChipInfo`
            A named tuple indicating the number of working cores, the states of
            all working cores, the set of working links and the size of the
            largest free block in SDRAM and SRAM.
        """
        info = self._send_scp(x, y, 0, SCPCommands.info, expected_args=3)

        # Unpack values encoded in the argument fields
        num_cores = info.arg1 & 0x1F
        working_links = set(link for link in Links
                            if (info.arg1 >> (8 + link)) & 1)
        largest_free_rtr_mc_block = (info.arg1 >> 14) & 0x7FF
        ethernet_up = bool(info.arg1 & (1 << 25))

        # Unpack the values in the data payload
        data = struct.unpack_from("<18BHI", info.data)
        core_states = [consts.AppState(c) for c in data[:18]]
        local_ethernet_chip = ((data[18] >> 8) & 0xFF,
                               (data[18] >> 0) & 0xFF)
        ip_address = ".".join(str((data[19] >> i) & 0xFF)
                              for i in range(0, 32, 8))

        return ChipInfo(
            num_cores=num_cores,
            core_states=core_states[:num_cores],
            working_links=working_links,
            largest_free_sdram_block=info.arg2,
            largest_free_sram_block=info.arg3,
            largest_free_rtr_mc_block=largest_free_rtr_mc_block,
            ethernet_up=ethernet_up,
            ip_address=ip_address,
            local_ethernet_chip=local_ethernet_chip,
        )

    @ContextMixin.use_contextual_arguments()
    def get_working_links(self, x, y):
        """Return the set of links reported as working.

        This command tests each of the links leaving a chip by sending a PEEK
        nearest-neighbour packet down each link to verify that the remote
        device is a SpiNNaker chip. If no reply is received via a given link or
        if the remote device is not a SpiNNaker chip, the link is reported as
        dead.

        See also: :py:meth:`.get_chip_info`.

        Returns
        -------
        set([:py:class:`rig.links.Links`, ...])
        """
        return self.get_chip_info(x, y).working_links

    @ContextMixin.use_contextual_arguments()
    def get_num_working_cores(self, x, y):
        """Return the number of working cores, including the monitor.

        See also: :py:meth:`.get_chip_info`.
        """
        return self.read_struct_field("sv", "num_cpus", x, y)

    @ContextMixin.use_contextual_arguments()
    def get_system_info(self, x=255, y=255):
        """Discover the integrity and resource availability of a whole
        SpiNNaker system.

        This command performs :py:meth:`.get_chip_info` on all working chips in
        the system returning an enhanced :py:class:`dict`
        (:py:class:`.SystemInfo`) containing a look-up from chip coordinate to
        :py:class:`.ChipInfo`. In addition to standard dictionary
        functionality, :py:class:`.SystemInfo` provides a number of convenience
        methods, which allow convenient iteration over various aspects of the
        information stored.

        .. note::
            This method replaces the deprecated :py:meth:`.get_machine` method.
            To build a :py:class:`~rig.place_and_route.Machine` for
            place-and-route purposes, the
            :py:func:`rig.place_and_route.utils.build_machine` utility function
            may be used with :py:meth:`.get_system_info` like so::

                >> from rig.place_and_route.utils import build_machine
                >> sys_info = mc.get_system_info()
                >> machine = build_machine(sys_info)

        Parameters
        ----------
        x : int
        y : int
            The coordinates of the chip from which system exploration should
            begin, by default (255, 255). Most users will not need to change
            these parameters.

        Returns
        -------
        :py:class:`.SystemInfo`
            An enhanced :py:class:`dict` object {(x, y): :py:class:`.ChipInfo`,
            ...} with a number of utility methods for accessing higher-level
            system information.
        """
        # A quick way of getting a list of working chips
        p2p_tables = self.get_p2p_routing_table(x, y)

        # Calculate the extent of the system
        max_x = max(x_ for (x_, y_), r in iteritems(p2p_tables)
                    if r != consts.P2PTableEntry.none)
        max_y = max(y_ for (x_, y_), r in iteritems(p2p_tables)
                    if r != consts.P2PTableEntry.none)

        sys_info = SystemInfo(max_x + 1, max_y + 1)

        for (x, y), p2p_route in iteritems(p2p_tables):
            if p2p_route != consts.P2PTableEntry.none:
                try:
                    sys_info[(x, y)] = self.get_chip_info(x, y)
                except SCPError:
                    # The chip was listed in the P2P table but is not
                    # responding. Assume it is dead and don't include it in
                    # the info returned.
                    pass

        return sys_info

    def get_machine(self, x=255, y=255, default_num_cores=18):
        """**Deprecated.** Probe the machine to discover which cores and links
        are working.

        .. warning::
            This method has been deprecated in favour of
            :py:meth:`.get_system_info` for getting information about the
            general resources available in a SpiNNaker machine. This method may
            be removed in the future.

            To build a :py:class:`~rig.place_and_route.Machine` for
            place-and-route purposes, the
            :py:func:`rig.place_and_route.utils.build_machine` utility function
            may be used with :py:meth:`.get_system_info` like so::

                >> from rig.place_and_route import build_machine
                >> sys_info = mc.get_system_info()
                >> machine = build_machine(sys_info)

            This method also historically used the size of the SDRAM and
            SRAM heaps to set the respective resource values in the
            :py:class:`~rig.place_and_route.Machine`. :py:meth:`.get_machine`
            since changed to reporting the size of the largest free block in
            the SDRAM and SRAM heaps on each chip. Most applications should not
            be negatively impacted by this change.

        .. note::
            The chip (x, y) supplied is the one where the search for working
            chips begins. Selecting anything other than (255, 255), the
            default, may be useful when debugging very broken machines.

        Parameters
        ----------
        default_num_cores : int
            This argument is ignored.

        Returns
        -------
        :py:class:`~rig.place_and_route.Machine`
            This Machine will include all cores reported as working by the
            system software with the following resources defined:

            :py:data:`~rig.place_and_route.Cores`
                Number of working cores on each chip (including the monitor
                core, any cores already running applications and idle cores).
            :py:data:`~rig.place_and_route.SDRAM`
                The size of the largest free block of SDRAM on the heap. This
                gives a conservative measure of how much SDRAM is free on a
                given chip (which will underestimate availability if the
                system's memory is highly fragmented.
            :py:data:`~rig.place_and_route.SRAM`
                The size of the largest free block of SRAM on the heap. This
                gives a conservative measure of how much SRAM is free on a
                given chip (which will underestimate availability if the
                system's memory is highly fragmented.
        """
        warnings.warn(
            "MachineController.get_machine() is deprecated, "
            "see get_system_info().", DeprecationWarning)

        from rig.place_and_route.utils import build_machine

        system_info = self.get_system_info(x, y)
        return build_machine(system_info)


class CoreInfo(collections.namedtuple(
    'CoreInfo', "position physical_cpu virt_cpu software_version buffer_size "
                "build_date version_string software_version_labels")):
    """Information returned about a core by sver.

    Parameters
    ----------
    position : (x, y)
        Logical location of the chip in the system.
    physical_cpu : int
        The physical ID of the core. (Not useful to most users).
    virt_cpu : int
        The virtual ID of the core. This is the number used by all high-level
        software APIs.
    software_version : (major, minor, patch)
        The numerical components of the software version number. See also:
        ``software_version_labels``.
    buffer_size : int
        Maximum supported size (in bytes) of the data portion of an SCP packet.
    build_date : int
        The time at which the software was compiled as a unix timestamp. May be
        zero if not set.
    version_string : string
        Human readable, textual version information split in to two fields by a
        "/". In the first field is the kernal (e.g. SC&MP or SARK) and the
        second the hardware platform (e.g. SpiNNaker).
    software_version_labels : string
        Any additional labels or build information associated with the software
        version. (See also: ``software_version`` and the `Semantic Versioning
        <http://semver.org/>`_ specification).
    """


class ChipInfo(collections.namedtuple(
    'ChipInfo', "num_cores core_states working_links "
                "largest_free_sdram_block largest_free_sram_block "
                "largest_free_rtr_mc_block ethernet_up ip_address "
                "local_ethernet_chip")):
    """Information returned about a chip.

    If some parameter is omitted from the constructor, realistic defaults are
    provided. These should only be used for writing tests and general
    applications should set all values based on reports from the SpiNNaker
    machine itself, e.g. using :py:meth:`~.MachineController.get_chip_info`.

    Parameters
    ----------
    num_cores : int
        The number of working cores on the chip.
    core_states : [:py:class:`~rig.machine_control.consts.AppState`, ...]
        The state of each working core in the machine in a list ``num_cores``
        in length.
    working_links : set([`rig.links.Links`, ...])
        The set of working links leaving that chip. For a link to be considered
        working, the link must work in both directions and the device at the
        far end must also be a SpiNNaker chip.
    largest_free_sdram_block : int
        The size (in bytes) of the largest free block of SDRAM.
    largest_free_sram_block : int
        The size (in bytes) of the largest free block of SRAM.
    largest_free_rtr_mc_block : int
        Number of entries in the largest free block of multicast router
        entries.
    ethernet_up : bool
        True if the chip's Ethernet connection is connected, False otherwise.
    ip_address : str
        The IP address of the Chip's Ethernet connection. If ethernet_up is
        False, the value of this field is unpredictable and should be ignored.
    local_ethernet_chip : (x, y)
        The coordinates of the 'nearest' Ethernet connected chip to this chip,
        corresponding with the value in ``sv->eth_addr``.

        .. note::

            This value may not literally be the *nearest* Ethernet connected
            chip. For example, it could be the Ethernet connected chip on the
            same board as the chip or chosen by the system at boot by some
            process which evenly balances load.
    """

    def __new__(cls,
                num_cores=18,
                core_states=None,
                working_links=set(Links),
                largest_free_sdram_block=119275492,
                largest_free_sram_block=22240,
                largest_free_rtr_mc_block=1023,
                ethernet_up=False,
                ip_address="0.0.0.0",
                local_ethernet_chip=(255, 255)):
        # If core_states is omitted, generate a list of core-states the right
        # length for the number of cores suggested)
        if core_states is None:
            core_states = ([consts.AppState.run] +
                           [consts.AppState.idle] * num_cores)[:-1]

        return super(ChipInfo, cls).__new__(
            cls, num_cores, core_states, working_links,
            largest_free_sdram_block, largest_free_sram_block,
            largest_free_rtr_mc_block, ethernet_up, ip_address,
            local_ethernet_chip)


class SystemInfo(dict):
    """An enhanced :py:class:`dict` containing a lookup from chip coordinates,
    (x, y), to chip information, :py:class:`.ChipInfo`.

    This dictionary contains an entry for every working chip in a system and no
    entry for chips which are dead. In addition to normal dictionary
    functionality, a number of utility methods are provided for iterating over
    useful information, for example individual cores and links.

    Attributes
    ----------
    width : int
        The width of the system in chips.
    height : int
        The height of the system in chips.
    """

    def __init__(self, width, height, *args, **kwargs):
        """Construct a :py:class:`.SystemInfo` object.

        Parameters
        ----------
        width : int
            The width of the system, in chips.
        height : int
            The height of the system, in chips.
        ...
            Remaining arguments are passed directly to the :py:class:`dict`
            constructor.
        """
        super(SystemInfo, self).__init__(*args, **kwargs)

        self.width = width
        self.height = height

    def chips(self):
        """Iterate over the coordinates of working chips.

        An alias for :py:meth:`.__iter__`, included for consistency.

        Yields
        ------
        (x, y)
            The coordinate of a working chip.
        """
        return iter(self)

    def ethernet_connected_chips(self):
        """Iterate over the coordinates of Ethernet connected chips.

        Yields
        ------
        ((x, y), str)
            The coordinate and IP address of each Ethernet connected chip in
            the system.
        """
        for xy, chip_info in six.iteritems(self):
            if chip_info.ethernet_up:
                yield (xy, chip_info.ip_address)

    def dead_chips(self):
        """Generate the coordinates of all dead chips.

        Yields
        ------
        (x, y)
            The coordinate of a dead chip.
        """
        for x in range(self.width):
            for y in range(self.height):
                if (x, y) not in self:
                    yield (x, y)

    def links(self):
        """Generate the coordinates of all working links.

        Yields
        ------
        (x, y, :py:class:`rig.links.Links`)
            A working link leaving a chip from the perspective of the chip. For
            example ``(0, 0, Links.north)`` would be the link going north from
            chip (0, 0) to chip (0, 1).
        """
        for (x, y), chip_info in iteritems(self):
            for link in chip_info.working_links:
                yield (x, y, link)

    def dead_links(self):
        """Generate the coordinates of all dead links leaving working chips.

        Any link leading to a dead chip will also be included in the list of
        dead links. In non-torroidal SpiNNaker sysmtes (e.g. single SpiNN-5
        boards), links on the periphery of the system will be marked as dead.

        Yields
        ------
        (x, y, :py:class:`rig.links.Links`)
            A working link leaving a chip from the perspective of the chip. For
            example ``(0, 0, Links.north)`` would be the link going north from
            chip (0, 0) to chip (0, 1).
        """
        for (x, y), chip_info in iteritems(self):
            for link in Links:
                if link not in chip_info.working_links:
                    yield (x, y, link)

    def cores(self):
        """Generate the set of all cores in the system.

        Yields
        ------
        (x, y, p, :py:class:`~rig.machine_control.consts.AppState`)
            A core in the machine, and its state. Cores related to a specific
            chip are yielded consecutively in ascending order of core number.
        """
        for (x, y), chip_info in iteritems(self):
            for p, state in enumerate(chip_info.core_states):
                yield (x, y, p, state)

    def __contains__(self, chip_core_or_link):
        """Test if a given chip, core or link is present and alive.

        Parameters
        ----------
        chip_core_or_link : tuple
            * If of the form (x, y, :py:class:`~rig.links.Links`), checks the
              link is present.
            * If of the form (x, y, p), checks the core is present.
            * If of the form (x, y, p,
              :py:class:`~rig.machine_control.consts.AppState`), checks the
              core is present and in the specified state.
            * If of the form (x, y), checks the chip is present.
        """
        if len(chip_core_or_link) == 2:
            return super(SystemInfo, self).__contains__(chip_core_or_link)
        elif (len(chip_core_or_link) == 3 and
              isinstance(chip_core_or_link[2], Links)):
            x, y, link = chip_core_or_link
            chip = self.get((x, y))
            return chip is not None and link in chip.working_links
        elif (len(chip_core_or_link) == 3 and
              isinstance(chip_core_or_link[2], six.integer_types)):
            x, y, p = chip_core_or_link
            chip = self.get((x, y))
            return chip is not None and 0 <= p < chip.num_cores
        elif len(chip_core_or_link) == 4:
            x, y, p, state = chip_core_or_link
            chip = self.get((x, y))
            return (chip is not None and
                    0 <= p < chip.num_cores and
                    chip.core_states[p] == state)
        else:
            raise ValueError(
                "Expect either (x, y) (x, y, p), (x, y, p, state) "
                "or (x, y, link).")


class ProcessorStatus(collections.namedtuple(
    "ProcessorStatus", "registers program_state_register stack_pointer "
                       "link_register rt_code phys_cpu cpu_state "
                       "mbox_ap_msg mbox_mp_msg mbox_ap_cmd mbox_mp_cmd "
                       "sw_count sw_file sw_line time app_name iobuf_address "
                       "app_id version user_vars")):
    """Information returned about the status of a processor.

    Parameters
    ----------
    registers : list
        Register values dumped during a runtime exception. (All zero by
        default.)
    program_status_register : int
        CPSR register (dumped during a runtime exception and zero by default).
    stack_pointer : int
        Stack pointer (dumped during a runtime exception and zero by default).
    link_register : int
        Link register (dumped during a runtime exception and zero by default).
    rt_code : :py:class:`~rig.machine_control.consts.RuntimeException`
        Code for any run-time exception which may have occurred.
    phys_cpu : int
        The physical CPU ID.
    cpu_state : :py:class:`~rig.machine_control.consts.AppState`
        Current state of the processor.
    mbox_ap_msg : int
    mbox_mp_msg : int
    mbox_ap_cmd : int
    mbox_mp_cmd : int
    sw_count : int
        Saturating count of software errors.  (Calls to `sw_err`).
    sw_file : int
        Pointer to a string containing the file name in which the last software
        error occurred.
    sw_line : int
        Line number of the last software error.
    time : int
        Time application was loaded.
    app_name : string
        Name of the application loaded to the processor core.
    iobuf_address : int
        Address of the output buffer used by the processor.
    app_id : int
        ID of the application currently running on the processor.
    version : (major, minor, patch)
        The version number of the application running on the core.
    user_vars : list
        List of 4 integer values that may be set by the user.
    """


class RouterDiagnostics(collections.namedtuple(
    "RouterDiagnostics", ["local_multicast", "external_multicast",
                          "local_p2p", "external_p2p",
                          "local_nearest_neighbour",
                          "external_nearest_neighbour",
                          "local_fixed_route", "external_fixed_route",
                          "dropped_multicast", "dropped_p2p",
                          "dropped_nearest_neighbour", "dropped_fixed_route",
                          "counter12", "counter13", "counter14", "counter15"])
                        ):
    """A namedtuple of values of a SpiNNaker router's 16 programmable
    diagnostic counters.

    Counter values can be accessed by subscripting::

        >>> diag = mc.get_router_diagnostics(0, 0)  # doctest: +SKIP
        >>> diag[0]                                 # doctest: +SKIP
        53491

    On boot, the first twelve counters are preconfigured to count commonly
    used information. As a convenience, these counter values can be selected by
    name::

        >>> diag.dropped_multicast  # doctest: +SKIP
        41

    .. note::

        It is possible to reconfigure *all* of the router counters to count
        arbitrary events (see the ``rFN`` register in section 10.11 of the
        SpiNNaker datasheet). If this has been done, using the subscript syntax
        for accessing counter values from this structure is strongly
        recommended.

    Parameters
    ----------
    local_multicast : int
    external_multicast : int
    local_p2p : int
    external_p2p : int
    local_nearest_neighbour : int
    external_nearest_neighbour : int
    local_fixed_route : int
    external_fixed_route : int
        For each of SpiNNaker's four packet types (multicast, point-to-point,
        nearest neighbour and fixed-route), there is:

        * A ``local_*`` counter which reports the number of packets routed
          which were sent by local application cores.
        * An ``external_*`` counter which reports the number of packets routed
          which were received from external sources (i.e. neighbouring chips).

        Any packets which were dropped by the router are not included in these
        counts.
    dropped_multicast : int
    dropped_p2p : int
    dropped_nearest_neighbour : int
    dropped_fixed_route : int
        These counters report the number of each type of packet which were
        dropped after arrival at this core.
    counter12 : int
    counter13 : int
    counter14 : int
    counter15 : int
        These counters are disabled by default.
    """


class IPTag(collections.namedtuple("IPTag",
                                   "addr mac port timeout flags count rx_port "
                                   "spin_addr spin_port")):
    """An IPTag as read from a SpiNNaker machine.

    Parameters
    ----------
    addr : str
        IP address SDP packets are forwarded to
    mac : int
    port : int
        Port number to forward SDP packets to
    timeout : int
    count : int
    rx_port : int
    spinn_addr : int
    spinn_port : int
    """
    @classmethod
    def from_bytestring(cls, bytestring):
        (ip, mac, port, timeout, flags, count, rx_port, spin_addr,
         spin_port) = struct.unpack("<4s 6s 3H I 2H B", bytestring[:25])
        # Convert the IP address into a string, otherwise save
        ip_addr = '.'.join(str(x) for x in struct.unpack("4B", ip))

        return cls(ip_addr, mac, port, timeout, flags, count, rx_port,
                   spin_addr, spin_port)


class SpiNNakerBootError(Exception):
    """Raised when attempting to boot a SpiNNaker machine has failed."""
    pass


class SpiNNakerMemoryError(Exception):
    """Raised when it is not possible to allocate memory on a SpiNNaker
    chip.

    Attributes
    ----------
    size : int
        The size of the failed allocation.
    chip : (x, y)
        The chip coordinates on which the allocation failed.
    tag : int
        The tag number of the failed allocation.
    """
    def __init__(self, size, x, y, tag=0):
        self.size = size
        self.chip = (x, y)
        self.tag = tag

    def __str__(self):
        if self.tag == 0:
            return ("Failed to allocate {} bytes of SDRAM on chip ({}, {}). "
                    "Insufficient memory available.".
                    format(self.size, self.chip[0], self.chip[1]))
        else:
            return ("Failed to allocate {} bytes of SDRAM on chip ({}, {}). "
                    "Insufficient memory available or tag {} already in use.".
                    format(self.size, self.chip[0], self.chip[1], self.tag))


class SpiNNakerRouterError(Exception):
    """Raised when it is not possible to allocated routing table entries on a
    SpiNNaker chip.

    Attributes
    ----------
    count : int
        The number of routing table entries requested.
    chip : (x, y)
        The coordinates of the chip the allocation failed on.
    """
    def __init__(self, count, x, y):
        self.count = count
        self.chip = (x, y)

    def __str__(self):
        return ("Failed to allocate {} routing table entries on chip ({}, {})".
                format(self.count, self.chip[0], self.chip[1]))


class SpiNNakerLoadingError(Exception):
    """Raised when it has not been possible to load applications to cores.

    Attributes
    ----------
    app_map : {"/path/to/app.aplx": {(x, y): {core, ...}, ...}, ...}
        The application map of the cores which could not be loaded.
    """
    def __init__(self, application_map):
        self.app_map = application_map

    def __str__(self):
        cores = []
        for app, targets in iteritems(self.app_map):
            for (x, y), ps in iteritems(targets):
                for p in ps:
                    cores.append("({}, {}, {})".format(x, y, p))
        return (
            "Failed to load applications to cores {}".format(", ".join(cores)))


def _if_not_closed(f):
    """Run the method iff. the memory view hasn't been closed and the parent
    object has not been freed."""
    @add_signature_to_docstring(f)
    @functools.wraps(f)
    def f_(self, *args, **kwargs):
        if self.closed or self._parent._freed:
            raise OSError
        return f(self, *args, **kwargs)

    return f_


class SlicedMemoryIO(object):
    """A file-like view into a subspace of the memory-space of a chip."""
    def __init__(self, parent, start_address, end_address):
        """Create a file-like view onto a subset of the memory-space of a chip.

        Parameters
        ----------
        parent : :py:class:`MemoryIO`
            Parent file-like view of memory. Only the parent `MemoryIO` may be
            freed.
        start_address : int
            Starting address in memory.
        end_address : int
            End address in memory.

        If `start_address` is greater or equal to `end_address` then
        `end_address` is ignored and `start_address` is used instead.
        """
        # Store parameters
        self.closed = False
        self._parent = parent

        # Store and clip the addresses
        self._start_address = start_address
        self._end_address = max(start_address, end_address)

        # Current offset from start address
        self._offset = 0

    def close(self):
        """Flush and close the file-like."""
        if not self.closed:
            self.flush()
            self.closed = True

    def __getitem__(self, sl):
        """Get a new file-like view of SDRAM covering the range indicated by
        the slice.

        For example, if `f` is a `MemoryIO` covering a 100 byte region of SDRAM
        then::

            >>> g = f[0:10]  # doctest: +SKIP

        Creates a new `MemoryIO` referring to just the first 10 bytes of `f`,
        the new file-like will be positioned at the start of the given block::

            >>> g.tell()  # doctest: +SKIP
            0

        Raises
        ------
        ValueError
            If the slice is not contiguous.
        """
        if isinstance(sl, slice) and (sl.step is None or sl.step == 1):
            # Get the start and end addresses
            if sl.start is None:
                start_address = self._start_address
            elif sl.start < 0:
                start_address = max(self._start_address,
                                    self._end_address + sl.start)
            else:
                start_address = min(self._end_address,
                                    self._start_address + sl.start)

            if sl.stop is None:
                end_address = self._end_address
            elif sl.stop < 0:
                end_address = max(start_address,
                                  self._end_address + sl.stop)
            else:
                end_address = min(self._end_address,
                                  self._start_address + sl.stop)

            # Construct the new file-like
            return SlicedMemoryIO(self._parent, start_address, end_address)
        else:
            raise ValueError("Can only make contiguous slices of MemoryIO")

    def __len__(self):
        """Return the number of bytes in the file-like view of SDRAM."""
        return self._end_address - self._start_address

    def __enter__(self):
        """Enter a new block which will call :py:meth:`~.close` when exited."""
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Exit a block and call :py:meth:`~.close`."""
        self.close()

    @_if_not_closed
    def read(self, n_bytes=-1):
        """Read a number of bytes from the memory.

        .. note::
            Reads beyond the specified memory range will be truncated.

        .. note::
            Produces a :py:exc:`.TruncationWarning` if fewer bytes are read
            than requested. These warnings can be converted into exceptions
            using :py:func:`warnings.simplefilter`::

                >>> import warnings
                >>> from rig.machine_control.machine_controller \\
                ...     import TruncationWarning
                >>> warnings.simplefilter('error', TruncationWarning)

        Parameters
        ----------
        n_bytes : int
            A number of bytes to read.  If the number of bytes is negative or
            omitted then read all data until the end of memory region.

        Returns
        -------
        :py:class:`bytes`
            Data read from SpiNNaker as a bytestring.
        """
        # If n_bytes is negative then calculate it as the number of bytes left
        if n_bytes < 0:
            n_bytes = self._end_address - self.address

        # Determine how far to read, then read nothing beyond that point.
        if self.address + n_bytes > self._end_address:
            new_n_bytes = self._end_address - self.address
            warnings.warn("read truncated from {} to {} bytes".format(
                n_bytes, new_n_bytes), TruncationWarning, stacklevel=3)
            n_bytes = new_n_bytes

        if n_bytes <= 0:
            return b''

        # Perform the read and increment the offset
        data = self._parent._perform_read(self.address, n_bytes)
        self._offset += n_bytes
        return data

    @_if_not_closed
    def write(self, bytes):
        """Write data to the memory.

        .. note::
            Writes beyond the specified memory range will be truncated and a
            :py:exc:`.TruncationWarning` is produced. These warnings can be
            converted into exceptions using :py:func:`warnings.simplefilter`::

                >>> import warnings
                >>> from rig.machine_control.machine_controller \\
                ...     import TruncationWarning
                >>> warnings.simplefilter('error', TruncationWarning)

        Parameters
        ----------
        bytes : :py:class:`bytes`
            Data to write to the memory as a bytestring.

        Returns
        -------
        int
            Number of bytes written.
        """
        if self.address + len(bytes) > self._end_address:
            n_bytes = self._end_address - self.address

            warnings.warn("write truncated from {} to {} bytes".format(
                len(bytes), n_bytes), TruncationWarning, stacklevel=3)
            bytes = bytes[:n_bytes]

        if len(bytes) == 0:
            return 0

        # Perform the write and increment the offset
        self._parent._perform_write(self.address, bytes)
        self._offset += len(bytes)
        return len(bytes)

    @_if_not_closed
    def flush(self):
        """Flush any buffered writes.

        This must be called to ensure that all writes to SpiNNaker made using
        this file-like object (and its siblings, if any) are completed.

        .. note::

            This method is included only for compatibility reasons and does
            nothing. Writes are not currently buffered.
        """
        pass

    @_if_not_closed
    def tell(self):
        """Get the current offset in the memory region.

        Returns
        -------
        int
            Current offset (starting at 0).
        """
        return self._offset

    @property
    @_if_not_closed
    def address(self):
        """Get the current hardware memory address (indexed from 0x00000000).
        """
        return self._offset + self._start_address

    @_if_not_closed
    def seek(self, n_bytes, from_what=os.SEEK_SET):
        """Seek to a new position in the memory region.

        Parameters
        ----------
        n_bytes : int
            Number of bytes to seek.
        from_what : int
            As in the Python standard: `0` seeks from the start of the memory
            region, `1` seeks from the current position and `2` seeks from the
            end of the memory region. For example::

                mem.seek(-1, 2)  # Goes to the last byte in the region
                mem.seek(-5, 1)  # Goes 5 bytes before that point
                mem.seek(0)      # Returns to the start of the region

            Note that `os.SEEK_END`, `os.SEEK_CUR` and `os.SEEK_SET` are also
            valid arguments.
        """
        if from_what == 0:
            self._offset = n_bytes
        elif from_what == 1:
            self._offset += n_bytes
        elif from_what == 2:
            self._offset = (self._end_address - self._start_address) - n_bytes
        else:
            raise ValueError(
                "from_what: can only take values 0 (from start), "
                "1 (from current) or 2 (from end) not {}".format(from_what)
            )


def _if_not_freed(f):
    """Run the method iff. the memory view hasn't been closed."""
    @add_signature_to_docstring(f)
    @functools.wraps(f)
    def f_(self, *args, **kwargs):
        if self._freed:
            raise OSError
        return f(self, *args, **kwargs)

    return f_


class MemoryIO(SlicedMemoryIO):
    """A file-like view into a subspace of the memory-space of a chip.

    A `MemoryIO` is sliceable to allow construction of new, more specific,
    file-like views of memory.

    For example::

        >>> # Read, write and seek through memory as if it was a file
        >>> f = MemoryIO(mc, 0, 1, 0x67800000, 0x6780000c)  # doctest: +SKIP
        >>> f.write(b"Hello, world")                        # doctest: +SKIP
        12
        >>> f.seek(0)                                       # doctest: +SKIP
        >>> f.read()                                        # doctest: +SKIP
        b"Hello, world"

        >>> # Slice the MemoryIO to produce a new MemoryIO which can only
        >>> # access a subset of the memory.
        >>> g = f[0:5]                                      # doctest: +SKIP
        >>> g.read()                                        # doctest: +SKIP
        b"Hello"
        >>> g.seek(0)                                       # doctest: +SKIP
        >>> g.write(b"Howdy, partner!")                     # doctest: +SKIP
        5
        >>> f.seek(0)                                       # doctest: +SKIP
        >>> f.read()                                        # doctest: +SKIP
        b"Howdy, world"
    """

    def __init__(self, machine_controller, x, y, start_address, end_address):
        """Create a file-like view onto a subset of the memory-space of a chip.

        Parameters
        ----------
        machine_controller : :py:class:`~.MachineController`
            A communicator to handle transmitting and receiving packets from
            the SpiNNaker machine.
        x : int
            x co-ordinate of the chip.
        y : int
            y co-ordinate of the chip.
        start_address : int
            Starting address in memory.
        end_address : int
            End address in memory.

        If `start_address` is greater or equal to `end_address` then
        `end_address` is ignored and `start_address` is used instead.
        """
        super(MemoryIO, self).__init__(parent=self,
                                       start_address=start_address,
                                       end_address=end_address)

        # Store parameters
        self._x = x
        self._y = y
        self._machine_controller = machine_controller
        self._freed = False

    @_if_not_freed
    def free(self):
        """Free the memory referred to by the file-like, any subsequent
        operations on this file-like or slices of it will fail.
        """
        # Free the memory
        self._machine_controller.sdram_free(self._start_address,
                                            self._x, self._y)

        # Mark as freed
        self._freed = True

    @_if_not_freed
    def _perform_read(self, addr, size):
        """Perform a read using the machine controller."""
        return self._machine_controller.read(addr, size, self._x, self._y, 0)

    @_if_not_freed
    def _perform_write(self, addr, data):
        """Perform a write using the machine controller."""
        return self._machine_controller.write(addr, data, self._x, self._y, 0)


class TruncationWarning(RuntimeWarning):
    """Warning produced when a reading/writing past the end of a
    :py:class:`MemoryIO` results in a truncated read/write.
    """


def unpack_routing_table_entry(packed):
    """Unpack a routing table entry read from a SpiNNaker machine.

    Parameters
    ----------
    packet : :py:class:`bytes`
        Bytes containing a packed routing table.

    Returns
    -------
    (:py:class:`~rig.routing_table.RoutingTableEntry`, app_id, core) or None
        Tuple containing the routing entry, the app_id associated with the
        entry and the core number associated with the entry; or None if the
        routing table entry is flagged as unused.
    """
    # Unpack the routing table entry
    _, free, route, key, mask = struct.unpack(consts.RTE_PACK_STRING, packed)

    # If the top 8 bits of the route are set then this entry is not in use, so
    # return None.
    if route & 0xff000000 == 0xff000000:
        return None

    # Convert the routing table entry
    routes = {r for r in routing_table.Routes if (route >> r) & 0x1}
    rte = routing_table.RoutingTableEntry(routes, key, mask)

    # Convert the surrounding data
    app_id = free & 0xff
    core = (free >> 8) & 0x0f

    return (rte, app_id, core)
