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

from .consts import SCPCommands, NNCommands, NNConstants, AppFlags, LEDAction
from . import boot, consts, regions, struct_file
from .scp_connection import SCPConnection

from rig.machine_control.scp_connection import SCPError

from rig import routing_table
from rig.machine import Cores, SDRAM, SRAM, Links, Machine

from rig.utils.contexts import ContextMixin, Required
from rig.utils.docstrings import add_signature_to_docstring


class MachineController(ContextMixin):
    """A high-level interface for controlling a SpiNNaker system.

    This class is essentially a wrapper around key functions provided by the
    SCP protocol which aims to straight-forwardly handle many of the difficult
    details and corner cases to ensure easy, efficient and reliable
    communication with a machine.

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
            board has not yet been booted, this will become chip (0, 0).
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

        # Load default structs if none provided
        self.structs = structs
        if self.structs is None:
            struct_data = pkg_resources.resource_string("rig",
                                                        "boot/sark.struct")
            self.structs = struct_file.read_struct_file(struct_data)

        # Create the initial connection
        self.connections = [
            SCPConnection(initial_host, scp_port, n_tries, timeout)
        ]

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
            data = self.get_software_version(0, 0)
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

    @ContextMixin.use_contextual_arguments(
        x=Required, y=Required, p=Required)
    def send_scp(self, *args, **kwargs):
        """Transmit an SCP Packet and return the response.

        This function is a thin wrapper around
        :py:meth:`rig.machine_control.scp_connection.SCPConnection.send_scp`.

        Future versions of this command will automatically choose the most
        appropriate connection to use for machines with more than one Ethernet
        connection.

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
        return self.connections[0]

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

    def boot(self, width, height, **boot_kwargs):
        """Boot a SpiNNaker machine of the given size.

        The system will be booted from the chip whose hostname was given as the
        argument to the MachineController.

        This method is a thin wrapper around
        :py:func:`rig.machine_control.boot.boot`.

        After booting, the structs in this MachineController will be set to
        those used to boot the machine.

        .. warning::
            This function does not check that the system has been booted
            successfully. This can be checked by ensuring that
            :py:meth:`.MachineController.get_software_version` returns a
            sensible value.

        .. warning::
            If the system has already been booted, this command will not cause
            the system to 'reboot' using the supplied firmware.

        .. warning::
            Booting the system over the open internet is likely to fail due to
            the port number being blocked by most ISPs and UDP not being
            reliable. A proxy such as `spinnaker_proxy
            <https://github.com/project-rig/spinnaker_proxy>`_ may be useful in
            this situation.

        Parameters
        ----------
        width : int
            Width of the machine (0 < w < 256)
        height : int
            Height of the machine (0 < h < 256)

        Notes
        -----
        The constants `rig.machine_control.boot.spinX_boot_options` can be used
        to specify boot parameters, for example::

            controller.boot(**spin3_boot_options)

        This is neccessary on boards such as SpiNN-3 boards if the more than
        LED 0 are required by an application since by default, only LED 0 is
        enabled.
        """
        boot_kwargs.setdefault("boot_port", self.boot_port)
        self.structs = boot.boot(self.initial_host, width=width, height=height,
                                 **boot_kwargs)
        assert len(self.structs) > 0

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
    def get_software_version(self, x, y, processor=0):
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

        # arg2 => version number and buffer size
        version = (sver.arg2 >> 16) / 100.
        buffer_size = (sver.arg2 & 0xffff)

        return CoreInfo(p2p_address, pcpu, vcpu, version, buffer_size,
                        sver.arg3, sver.data.decode("utf-8"))

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
        specified core."""
        # The IOBUF data is stored in a linked-list of blocks of memory in
        # SDRAM. The size of each block is given in SV
        iobuf_size = self.read_struct_field("sv", "iobuf_size", x, y)

        # The first block in the list is given in the core's VCPU field
        address = self.read_vcpu_struct_field("iobuf", x, y, p)

        iobuf = ""

        while address:
            # The IOBUF data is proceeded by a header which gives the next
            # address and also the length of the string in the current buffer.
            iobuf_data = self.read(address, iobuf_size + 16, x, y)
            address, time, ms, length = struct.unpack("<4I", iobuf_data[:16])
            iobuf += iobuf_data[16:16 + length].decode("utf-8")

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
    def sdram_alloc(self, size, tag=0, x=Required, y=Required,
                    app_id=Required):
        """Allocate a region of SDRAM for an application.

        Requests SARK to allocate a block of SDRAM for an application. This
        allocation will be freed when the application is stopped.

        Parameters
        ----------
        size : int
            Number of bytes to attempt to allocate in SDRAM.
        tag : int
            8-bit (chip-wide) tag that can be looked up by a SpiNNaker
            application to discover the address of the allocated block.  If `0`
            then no tag is applied.

        Returns
        -------
        int
            Address of the start of the region.

        Raises
        ------
        SpiNNakerMemoryError
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
        return rv.arg1

    @ContextMixin.use_contextual_arguments()
    def sdram_alloc_as_filelike(self, size, tag=0, x=Required, y=Required,
                                app_id=Required, buffer_size=0):
        """Like :py:meth:`.sdram_alloc` but returns a file-like object which
        allows safe reading and writing to the block that is allocated.

        Other Parameters
        ----------------
        buffer_size : int
            The number of bytes to store in the write buffer for the file-like.
            If this is set to anything but `0` (the default) then
            :py:meth:`~.MemoryIO.flush` should be called to ensure that all
            writes are completed.

        Returns
        -------
        :py:class:`.MemoryIO`
            File-like object which allows accessing the newly allocated region
            of memory.

        Raises
        ------
        SpiNNakerMemoryError
            If the memory cannot be allocated, or the tag is already taken or
            invalid.
        """
        # Perform the malloc
        start_address = self.sdram_alloc(size, tag, x, y, app_id)

        return MemoryIO(self, x, y, start_address, start_address + size,
                        buffer_size=buffer_size)

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
            0, 0, 0, SCPCommands.nearest_neighbour_packet,
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
        self._send_scp(0, 0, 0, SCPCommands.nearest_neighbour_packet,
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
            self._send_scp(0, 0, 0, SCPCommands.flood_fill_data,
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
        self._send_scp(0, 0, 0, SCPCommands.nearest_neighbour_packet,
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
            guaranteed to arrive. The effect of this is one of the following:

            * Some regions may be included/excluded incorrectly.
            * Some chips will not receive the complete application binary and
              will silently not execute the binary.

            As a result, the user is responsible for checking that each core
            was successfully loaded with the correct binary. At present, the
            two recommended approaches to this are:

            * The user should check that the correct number of application
              binaries reach their initial barrier (SYNC0), when this facility
              is used. This is not fool-proof but will flag up all but
              situations where exactly the right number, but the wrong
              selection of cores were loaded. (At the time of writing, this
              situation is not possible but will become a concern in future
              versions of SC&MP.
            * The user can check the process list of each chip to ensure the
              application was loaded into the correct set of cores.

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
            # ascending order.
            fills = list(regions.compress_flood_fill_regions(targets))
            fills.sort(key=lambda rc: (rc[0] << 18) | rc[1])

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
                "sv", "sdram_sys", 0, 0)
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
        attempts, an exception will be raised.

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

        # XXX If the signal is "stop", then we first remove all routing table
        # entries associated with the application ID. This code will be
        # unnecessaru when SpiNNaker tools 1.4 becomes available.
        if signal is consts.AppSignal.stop:
            # Get a machine object so we can determine where we need to remove
            # the routing tables.
            mcn = self.get_machine()

            # Now remove all routing entries:
            for (x, y) in mcn:
                self.clear_routing_table_entries(x, y, app_id)

        # Construct the packet for transmission
        arg1 = consts.signal_types[signal]
        arg2 = (signal << 16) | 0xff00 | app_id
        arg3 = 0x0000ffff  # Meaning "transmit to all"
        self._send_scp(0, 0, 0, SCPCommands.signal, arg1, arg2, arg3)

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
            0, 0, 0, SCPCommands.signal, arg1, arg2, arg3).arg1

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
            :py:func:`~rig.place_and_route.util.build_routing_tables`.

        Raises
        ------
        SpiNNakerRouterError
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
        SpiNNakerRouterError
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
    def get_working_links(self, x, y):
        """Return the set of links reported as working.

        The returned set lists only links over-which nearest neighbour
        peek/poke commands could be sent. This means that links connected to
        peripherals may falsely be omitted.

        Returns
        -------
        set([:py:class:`rig.machine.Links`, ...])
        """
        link_up = self.read_struct_field("sv", "link_up", x, y)
        return set(link for link in Links if link_up & (1 << link))

    @ContextMixin.use_contextual_arguments()
    def get_num_working_cores(self, x, y):
        """Return the number of working cores, including the monitor."""
        return self.read_struct_field("sv", "num_cpus", x, y)

    def get_machine(self, x=0, y=0, default_num_cores=18):
        """Probe the machine to discover which cores and links are working.

        .. note::
            Links are reported as dead when the device at the other end of the
            link does not respond to SpiNNaker nearest neighbour packets. This
            may thus mistakenly report links attached to peripherals as dead.

        .. note::
            The probing process does not report how much memory is free, nor
            how many processors are idle but rather the total available.

        .. note::
            The size of the SDRAM and SysRAM heaps is assumed to be the same
            for all chips and is only checked on chip (x, y).

        .. note::
            The chip (x, y) supplied is the one which will be where the search
            for working chips begins. Selecting anything other than (0, 0), the
            default, may be useful when debugging very broken machines.

        Parameters
        ----------
        default_num_cores : int
            The number of cores generally available on a SpiNNaker chip
            (including the monitor).

        Returns
        -------
        :py:class:`~rig.machine.Machine`
            This Machine will include all cores reported as working by the
            system software with the following resources defined:

            :py:data:`~rig.machine.Cores`
                Number of cores working on each chip (including the monitor
                core).
            :py:data:`~rig.machine.SDRAM`
                The size of the SDRAM heap.
            :py:data:`~rig.machine.SRAM`
                The size of the SysRAM heap.
        """
        p2p_tables = self.get_p2p_routing_table(x, y)

        # Calculate the extent of the system
        max_x = max(x_ for (x_, y_), r in iteritems(p2p_tables)
                    if r != consts.P2PTableEntry.none)
        max_y = max(y_ for (x_, y_), r in iteritems(p2p_tables)
                    if r != consts.P2PTableEntry.none)

        # Discover the heap sizes available for memory allocation
        sdram_start = self.read_struct_field("sv", "sdram_heap", x, y)
        sdram_end = self.read_struct_field("sv", "sdram_sys", x, y)
        sysram_start = self.read_struct_field("sv", "sysram_heap", x, y)
        sysram_end = self.read_struct_field("sv", "vcpu_base", x, y)

        chip_resources = {Cores: default_num_cores,
                          SDRAM: sdram_end - sdram_start,
                          SRAM: sysram_end - sysram_start}
        dead_chips = set()
        dead_links = set()
        chip_resource_exceptions = {}

        # Discover dead links and cores
        for (x, y), p2p_route in iteritems(p2p_tables):
            if x <= max_x and y <= max_y:
                if p2p_route == consts.P2PTableEntry.none:
                    dead_chips.add((x, y))
                else:
                    try:
                        num_working_cores = self.get_num_working_cores(x, y)
                        working_links = self.get_working_links(x, y)

                        if num_working_cores < default_num_cores:
                            resource_exception = chip_resources.copy()
                            resource_exception[Cores] = min(default_num_cores,
                                                            num_working_cores)
                            chip_resource_exceptions[(x, y)] = \
                                resource_exception

                        for link in set(Links) - working_links:
                            dead_links.add((x, y, link))
                    except SCPError:
                        # The chip was listed in the P2P table but is not
                        # responding. Assume it is dead anyway.
                        dead_chips.add((x, y))

        return Machine(max_x + 1, max_y + 1,
                       chip_resources,
                       chip_resource_exceptions,
                       dead_chips, dead_links)


class CoreInfo(collections.namedtuple(
    'CoreInfo', "position physical_cpu virt_cpu version buffer_size "
                "build_date version_string")):
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
    version : float
        Software version number. (Major version is integral part, minor version
        is fractional part).
    buffer_size : int
        Maximum supported size (in bytes) of the data portion of an SCP packet.
    build_date : int
        The time at which the software was compiled as a unix timestamp. May be
        zero if not set.
    version_string : string
        Human readable, textual version information split in to two fields by a
        "/". In the first field is the kernal (e.g. SC&MP or SARK) and the
        second the hardware platform (e.g. SpiNNaker).
    """


class ProcessorStatus(collections.namedtuple(
    "ProcessorStatus", "registers program_state_register stack_pointer "
                       "link_register rt_code cpu_flags cpu_state "
                       "mbox_ap_msg mbox_mp_msg mbox_ap_cmd mbox_mp_cmd "
                       "sw_count sw_file sw_line time app_name iobuf_address "
                       "app_id user_vars")):
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
    cpu_flags : int
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
    """Read out of the diagnostic counters of a SpiNNaker router."""


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


class SpiNNakerMemoryError(Exception):
    """Raised when it is not possible to allocate memory on a SpiNNaker
    chip.
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
    """
    def __init__(self, count, x, y):
        self.count = count
        self.chip = (x, y)

    def __str__(self):
        return ("Failed to allocate {} routing table entries on chip ({}, {})".
                format(self.count, self.chip[0], self.chip[1]))


class SpiNNakerLoadingError(Exception):
    """Raised when it has not been possible to load applications to cores."""
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
    """Run the method iff. the memory view hasn't been closed."""
    @add_signature_to_docstring(f)
    @functools.wraps(f)
    def f_(self, *args, **kwargs):
        if self.closed:
            raise OSError
        return f(self, *args, **kwargs)

    return f_


class MemoryIO(object):
    """A file-like view into a subspace of the memory-space of a chip.

    A `MemoryIO` is sliceable to allow construction of new, more specific,
    file-like views of memory.

    For example::

        >>> f = MemoryIO(mc, 0, 1, 0x67800000, 0x6780000c)  # doctest: +SKIP
        >>> f.write(b"Hello, world")                        # doctest: +SKIP
        >>> f.read()                                        # doctest: +SKIP
        b"Hello, world"
        >>> g = f[0:5]                                      # doctest: +SKIP
        >>> g.read()                                        # doctest: +SKIP
        b"Hello"
    """

    def __init__(self, machine_controller, x, y, start_address, end_address,
                 buffer_size=0, _write_buffer=None):
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
        buffer_size : int
            Number of bytes to store in the write buffer.
        _write_buffer : :py:class:`._WriteBufferChild`
            Internal use only, the write buffer to use to combine writes.

        If `start_address` is greater or equal to `end_address` then
        `end_address` is ignored and `start_address` is used instead.
        """
        # Store parameters
        self.closed = False
        self._x = x
        self._y = y
        self._machine_controller = machine_controller

        # Get, or create, a write buffer
        if _write_buffer is None:
            _write_buffer = _WriteBuffer(x, y, 0, machine_controller,
                                         buffer_size)
        self._write_buffer = _write_buffer

        # Store and clip the addresses
        self._start_address = start_address
        self._end_address = max(start_address, end_address)

        # Current offset from start address
        self._offset = 0

    @property
    def buffer_size(self):
        """Return the number of bytes in the write buffer."""
        return self._write_buffer.buffer_size

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
            return type(self)(
                self._machine_controller, self._x, self._y,
                start_address, end_address,
                _write_buffer=self._write_buffer
            )
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
        # Flush this write buffer
        self.flush()

        # If n_bytes is negative then calculate it as the number of bytes left
        if n_bytes < 0:
            n_bytes = self._end_address - self.address

        # Determine how far to read, then read nothing beyond that point.
        if self.address + n_bytes > self._end_address:
            n_bytes = min(n_bytes, self._end_address - self.address)

        if n_bytes <= 0:
            return b''

        # Perform the read and increment the offset
        data = self._machine_controller.read(
            self.address, n_bytes, self._x, self._y, 0)
        self._offset += n_bytes
        return data

    @_if_not_closed
    def write(self, bytes):
        """Write data to the memory.

        .. warning::
            If the buffer size is not zero then writes may be buffered (and
            even overwritten) before being written to the machine.
            :py:meth:`~.flush` must be called to ensure that all writes are
            completed when required.

        .. note::
            Writes beyond the specified memory range will be truncated.

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
            n_bytes = min(len(bytes), self._end_address - self.address)

            if n_bytes <= 0:
                return 0

            bytes = bytes[:n_bytes]

        # Perform the write and increment the offset
        self._write_buffer.add_new_write(self.address, bytes)
        self._offset += len(bytes)
        return len(bytes)

    @_if_not_closed
    def flush(self):
        """Flush any buffered writes.

        This must be called to ensure that all writes to SpiNNaker made using
        this file-like object (and its siblings, if any) are completed.
        """
        self._write_buffer.flush()

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


class _WriteBuffer(object):
    """Write buffer used by :py:class:`.MemoryIO` to combine multiple writes
    together.
    """

    def __init__(self, x, y, p, controller, buffer_size=0):
        self.x = x
        self.y = y
        self.p = p
        self.controller = controller

        # A buffer of writes
        self.buffer = bytearray(buffer_size)
        self.start_address = None

        self.current_end = 0
        self.buffer_size = buffer_size

    def add_new_write(self, start_address, data):
        """Add a new write to the buffer."""
        if len(data) > self.buffer_size:
            # Perform the write if we couldn't buffer it at all
            self.flush()  # Flush to ensure ordering is preserved
            self.controller.write(start_address, data,
                                  self.x, self.y, self.p)
            return

        if self.start_address is None:
            # No value currently buffered, add this one
            self.start_address = start_address

        # If we can fit this write into the buffer then include it,
        # otherwise we flush the current buffer and start again
        start_offset = start_address - self.start_address
        end_offset = start_offset + len(data)  # Byte AFTER the end of the data

        if start_offset < 0:
            # The write starts from before this buffer, so we flush and add a
            # new write
            self.flush()
            self.add_new_write(start_address, data)
        elif (start_offset <= self.current_end and
                end_offset <= self.buffer_size):
            # The write is entirely contained within the buffer and starts
            # within the area of the buffer which already contains data, so we
            # can just modify the buffer.
            self.buffer[start_offset:end_offset] = data
            self.current_end = max(end_offset, self.current_end)
        else:
            # The write either starts outside the used area of the buffer, or
            # would overflow the buffer.
            if (start_offset < self.buffer_size and
                    start_offset <= self.current_end):
                # We would overflow the buffer, so store as much into the
                # buffer as possible.
                end = self.buffer_size - start_offset
                self.buffer[start_offset:] = data[:end]
                self.current_end = self.buffer_size

                # Then prepare the next block of data for buffering
                start_address += end
                data = data[end:]

            # Flush the buffer before storing the next write
            self.flush()
            self.add_new_write(start_address, data)

    def flush(self):
        """Write the current buffer out."""
        if self.start_address is not None:
            # Write out all the values from the buffer
            self.controller.write(
                self.start_address, self.buffer[:self.current_end],
                self.x, self.y, self.p
            )

            # Reset the buffer
            self.start_address = None
            self.current_end = 0


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
