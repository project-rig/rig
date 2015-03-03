import collections
from six import iteritems
import socket
import struct

from .consts import SCPCommands, DataType, NNCommands, NNConstants
from . import boot, consts, regions
from .scp_connection import SCPConnection
from rig.utils.contexts import ContextMixin, Required


class MachineController(ContextMixin):
    """TODO

    Attributes
    ----------
    """
    def __init__(self, initial_host, n_tries=5, timeout=0.5,
                 initial_context={"app_id": 30, "app_flags": {}}):
        """Create a new controller for a SpiNNaker machine.

        Parameters
        ----------
        initial_host : string
            Hostname or IP address of the SpiNNaker chip to connect to. If the
            board has not yet been booted, this will become chip (0, 0).
        n_tries : int
            Number of SDP packet retransmission attempts.
        timeout : float
        initial_context : `{argument: value}`
            Dictionary of default arguments to pass to methods in this class.
        """
        # Initialise the context stack
        ContextMixin.__init__(self, initial_context)

        # Store the initial parameters
        self.initial_host = initial_host
        self.n_tries = n_tries
        self.timeout = timeout
        self._nn_id = 0  # ID for nearest neighbour packets

        # Empty structs until booted, or otherwise set
        self.structs = {}

        # Create the initial connection
        self.connections = [
            SCPConnection(initial_host, n_tries, timeout)
        ]

    def __call__(self, **context_args):
        """Create a new context for use with `with`.

        E.g::

            with controller(x=3, y=4):
                # All commands will now communicate with chip (3, 4)
        """
        return self.get_new_context(**context_args)

    @ContextMixin.require_named_contextual_arguments("x", "y", "p")
    def send_scp(self, *args, **kwargs):
        """Transmit an SCP Packet.

        See the arguments for
        :py:method:`~rig.machine_control.scp_connection.SCPConnection` for
        details.
        """
        # Retrieve contextual arguments from the keyword arguments.  The
        # context system ensures that these values are present.
        x = kwargs.pop("x")
        y = kwargs.pop("y")
        p = kwargs.pop("p")
        return self._send_scp(x, y, p, *args, **kwargs)

    def _send_scp(self, x, y, p, *args, **kwargs):
        """Determine the best connection to use to send an SCP packet and use
        it to transmit.

        See the arguments for
        :py:method:`~rig.machine_control.scp_connection.SCPConnection` for
        details.
        """
        return self.connections[0].send_scp(x, y, p, *args, **kwargs)

    def boot(self, width, height, **boot_kwargs):
        """Boot a SpiNNaker machine of the given size.

        Parameters
        ----------
        width : int
            Width of the machine (0 < w < 256)
        height : int
            Height of the machine (0 < h < 256)

        For further boot arguments see
        :py:func:`~rig.machine_control.boot.boot`.

        Notes
        -----
        The constants `rig.machine_control.boot.spinX_boot_options` can be used
        to specify boot parameters, for example::

            controller.boot(**spin5_boot_options)

        Will boot the Spin5 board connected to by `controller`.
        """
        self.structs = boot.boot(self.initial_host, width=width, height=height,
                                 **boot_kwargs)

    @ContextMixin.use_contextual_arguments
    def get_software_version(self, x=Required, y=Required, processor=0):
        """Get the software version for a given SpiNNaker core.

        Returns
        -------
        :py:class:`CoreInfo`
            Information about the software running on a core.
        """
        sver = self._send_scp(x, y, processor, SCPCommands.sver)

        # Format the result
        # arg1 => p2p address, physical cpu, virtual cpu
        p2p = sver.arg1 >> 16
        pcpu = (sver.arg1 >> 8) & 0xff
        vcpu = sver.arg1 & 0xff

        # arg2 => version number and buffer size
        version = (sver.arg2 >> 16) / 100.
        buffer_size = (sver.arg2 & 0xffff)

        return CoreInfo(p2p, pcpu, vcpu, version, buffer_size, sver.arg3,
                        sver.data)

    @ContextMixin.use_contextual_arguments
    def write(self, address, data, x=Required, y=Required, p=0):
        """Write a bytestring to an address in memory.

        Parameters
        ----------
        address : int
            The address at which to start writing the data.
        data : :py:class:`bytes`
            Data to write into memory.
        """
        # While there is still data perform a write: get the block to write
        # this time around, determine the data type, perform the write and
        # increment the address
        while len(data) > 0:
            block, data = (data[:consts.SCP_DATA_LENGTH],
                           data[consts.SCP_DATA_LENGTH:])
            dtype = address_length_dtype[(address % 4, len(block) % 4)]
            self._write(x, y, p, address, block, dtype)
            address += len(block)

    def _write(self, x, y, p, address, data, data_type=DataType.byte):
        """Write an SCP command's worth of data to an address in memory.

        It is better to use :py:func:`~.write` which wraps this method and
        allows writing bytestrings of arbitrary length.

        Parameters
        ----------
        address : int
            The address at which to start writing the data.
        data : :py:class:`bytes`
            Data to write into memory.  Must be <= the amount accepted by the
            receiving core.
        data_type : :py:class:`~rig.machine_control.consts.DataType`
            The size of the data to write into memory.
        """
        length_bytes = len(data)
        self._send_scp(x, y, p, SCPCommands.write, address, length_bytes,
                       int(data_type), data, expected_args=0)

    @ContextMixin.use_contextual_arguments
    def read(self, address, length_bytes, x=Required, y=Required, p=0):
        """Read a bytestring from an address in memory.

        Parameters
        ----------
        address : int
            The address at which to start reading the data.
        length_bytes : int
            The number of bytes to read from memory.

        Returns
        -------
        :py:class:`bytes`
            The data is read back from memory as a bytestring.
        """
        # Make calls to the lower level read method until we have read
        # sufficient bytes.
        data = b''
        while len(data) < length_bytes:
            # Determine the number of bytes to read
            reads = min(consts.SCP_DATA_LENGTH, length_bytes - len(data))

            # Determine the data type to use
            dtype = address_length_dtype[(address % 4, reads % 4)]

            # Perform the read and increment the address
            data += self._read(x, y, p, address, reads, dtype)
            address += reads

        return data

    def _read(self, x, y, p, address, length_bytes, data_type=DataType.byte):
        """Read an SCP command's worth of data from an address in memory.

        It is better to use :py:func:`~.read` which wraps this method and
        allows reading bytestrings of arbitrary length.

        Parameters
        ----------
        address : int
            The address at which to start reading the data.
        length_bytes : int
            The number of bytes to read from memory, must be <= SCP_DATA_LENGTH
        data_type : DataType
            The size of the data to write into memory.

        Returns
        -------
        :py:class:`bytes`
            The data is read back from memory as a bytestring.
        """
        read_scp = self._send_scp(x, y, p, SCPCommands.read, address,
                                  length_bytes, int(data_type),
                                  expected_args=0)
        return read_scp.data

    @ContextMixin.use_contextual_arguments
    def read_struct_field(self, struct_name, field_name,
                          x=Required, y=Required, p=0):
        """Read the value out of a struct maintained by SARK.

        Parameters
        ----------
        struct_name : :py:class:`bytes`
            Name of the struct to read from, e.g., `b"sv"`
        field_name : :py:class:`bytes`
            Name of the field to read, e.g., `b"eth_addr"`

        .. note::
            The value returned is unpacked given the struct specification.

        .. warning::
            This feature is only available if this machine controller was used
            to boot a board OR an appropriate struct definition has been
            provided.  To do this use, e.g::

                from rig.machine_controller.struct_file import read_struct_file

                with open("/path/to/struct/spec", "rb") as f:
                    data = f.read()

                cn.structs = read_struct_file(data)

            Currently arrays are returned as tuples, e.g.::

                # Returns a 20-tuple.
                cn.read_struct_field(b"sv", b"status_map")

                # Fails
                cn.read_struct_field(b"sv", b"status_map[1]")
        """
        # Look up the struct and field
        field = self.structs[struct_name][field_name]

        address = self.structs[struct_name].base + field.offset
        pack_chars = field.length * field.pack_chars  # NOTE Python 2 and 3 fix
        length = struct.calcsize(pack_chars)

        # Perform the read
        data = self.read(address, length, x, y, p)

        # Unpack the data
        unpacked = struct.unpack(pack_chars, data)

        if field.length == 1:
            return unpacked[0]
        else:
            return unpacked

    @ContextMixin.use_contextual_arguments
    def iptag_set(self, iptag, addr, port, x=Required, y=Required):
        """Set the value of an IPTag.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to set
        addr : string
            IP address or hostname that the IPTag should point at.
        port : int
            Port that the IPTag should direct packets to.
        """
        # Format the IP address
        ip_addr = struct.pack('!4B',
                              *map(int, socket.gethostbyname(addr).split('.')))
        self._send_scp(x, y, 0, SCPCommands.iptag,
                       int(consts.IPTagCommands.set) << 16 | iptag,
                       port, struct.unpack('<I', ip_addr)[0])

    @ContextMixin.use_contextual_arguments
    def iptag_get(self, iptag, x=Required, y=Required):
        """Get the value of an IPTag.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to get

        Returns
        -------
        :py:class:`IPTag`
            The IPTag returned from SpiNNaker.
        """
        ack = self._send_scp(x, y, 0, SCPCommands.iptag,
                             int(consts.IPTagCommands.get) << 16 | iptag, 1,
                             expected_args=0)
        return IPTag.from_bytestring(ack.data)

    @ContextMixin.use_contextual_arguments
    def iptag_clear(self, iptag, x=Required, y=Required):
        """Clear an IPTag.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to clear.
        """
        self._send_scp(x, y, 0, SCPCommands.iptag,
                       int(consts.IPTagCommands.clear) << 16 | iptag)

    @ContextMixin.use_contextual_arguments
    def set_led(self, led, action=consts.LEDAction.toggle,
                x=Required, y=Required):
        """Toggle the state of an LED.

        Parameters
        ----------
        led : int
            Number of the LED to set the state of (0-3)
        action : :py:class:`rig.machine_control.consts.LEDAction`
            Action to perform on the LED (on, off or toggle [default])
        """
        arg1 = int(action) << (led * 2)
        self._send_scp(x, y, 0, SCPCommands.led, arg1=arg1, expected_args=0)

    @ContextMixin.use_contextual_arguments
    def sdram_alloc(self, size, tag=0, x=Required, y=Required,
                    app_id=Required):
        """Allocate a region of SDRAM for the given application.

        Parameters
        ----------
        size : int
            Number of bytes to attempt to allocate in SDRAM.
        tag : int
            8-bit tag that can be used identify the region of memory later.  If
            `0` then no tag is applied.

        Returns
        -------
        int
            Address of the start of the region.

        Raises
        ------
        SpiNNakerMemoryError
            If the memory cannot be allocated, or the tag is already taken or
            invalid.
        """
        assert 0 <= tag < 256

        # Construct arg1 (op_code << 8) | app_id
        arg1 = consts.AllocOperations.alloc_sdram << 8 | app_id

        # Send the packet and retrieve the address
        rv = self._send_scp(x, y, 0, SCPCommands.alloc_free, arg1, size, tag)
        if rv.arg1 == 0:
            # Allocation failed
            raise SpiNNakerMemoryError(size, x, y)
        return rv.arg1

    @ContextMixin.use_contextual_arguments
    def sdram_alloc_as_io(self, size, tag=0, x=Required, y=Required,
                          app_id=Required):
        """Like :py:meth:`.sdram_alloc` but a file-like object which allows
        reading and writing to the region is returned.

        Returns
        -------
        :py:class:`~MemoryIO`
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

        return MemoryIO(self, x, y, start_address, start_address + size)

    def _get_next_nn_id(self):
        """Get the next nearest neighbour ID."""
        self._nn_id = self._nn_id + 1 if self._nn_id < 126 else 1
        return self._nn_id * 2

    def _send_ffs(self, pid, region, n_blocks, fr):
        """Send a flood-fill start packet."""
        sfr = fr | (1 << 31)
        self._send_scp(
            0, 0, 0, SCPCommands.nearest_neighbour_packet,
            (NNCommands.flood_fill_start << 24) | (pid << 16) |
            (n_blocks << 8),
            region, sfr
        )

    def _send_ffd(self, pid, aplx_data, address):
        """Send flood-fill data packets."""
        block = 0
        while len(aplx_data) > 0:
            # Get the next block of data, send and progress the block
            # counter and the address
            data, aplx_data = (aplx_data[:consts.SCP_DATA_LENGTH],
                               aplx_data[consts.SCP_DATA_LENGTH:])
            size = len(data) // 4 - 1

            arg1 = (NNConstants.forward << 24 | NNConstants.retry << 16 | pid)
            arg2 = (block << 16) | (size << 8)
            self._send_scp(0, 0, 0, SCPCommands.flood_fill_data,
                           arg1, arg2, address, data)

            # Increment the address and the block counter
            block += 1
            address += len(data)

    def _send_ffe(self, pid, app_id, app_flags, cores, fr):
        """Send a flood-fill end packet."""
        arg1 = (NNCommands.flood_fill_end << 24) | pid
        arg2 = (app_id << 24) | (app_flags << 18) | (cores & 0x3fff)
        self._send_scp(0, 0, 0, SCPCommands.nearest_neighbour_packet,
                       arg1, arg2, fr)

    @ContextMixin.require_named_contextual_arguments("app_id", "app_flags")
    def load_aplx(self, *args, **kwargs):
        """Load an APLX to a set of application cores.

        If a :py:class:`str` APLX filename is the first argument then the
        second is assumed to be a dictionary mapping {(x, y): set([cores]),
        ...}.  Otherwise the return value of
        :py:func:`~rig.place_and_route.util.build_application_map` may be used
        directly.

        An `app_id` can be entered as a keyword argument OR from a context.::

            # Either
            controller.load_aplx(targets, app_id=30)

            # Or
            with controller(app_id=30):
                # ...
                controller.load_aplx(targets)
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
                "load_aplx: accepts either 1 or 2 positional arguments: a map "
                "of filenames to targets OR a single filename and its targets"
            )

        # Get the application ID, the context system will guarantee that this
        # is available, likewise the application flags.
        app_id = kwargs.pop("app_id")
        app_flags = kwargs.pop("app_flags")

        flags = 0x0000
        for flag in app_flags:
            flags |= flag

        # The forward and retry parameters
        fr = NNConstants.forward << 8 | NNConstants.retry

        # Load each APLX in turn
        for (aplx, targets) in iteritems(application_map):
            # Determine the minimum number of flood-fills that are necessary to
            # load the APLX using level-3 regions.
            fills = regions.get_minimal_flood_fills(targets)

            # Load the APLX data
            with open(aplx, "rb+") as f:
                aplx_data = f.read()
            n_blocks = ((len(aplx_data) + consts.SCP_DATA_LENGTH - 1) //
                        consts.SCP_DATA_LENGTH)

            # Perform each flood-fill.
            for (region, cores) in fills:
                # Get an index for the nearest neighbour operation
                pid = self._get_next_nn_id()

                # Send the flood-fill start packet
                self._send_ffs(pid, region, n_blocks, fr)

                # Send the data
                self._send_ffd(pid, aplx_data, consts.SARK_DATA_BASE)

                # Send the flood-fill END packet
                self._send_ffe(pid, app_id, flags, cores, fr)


class CoreInfo(collections.namedtuple(
    'CoreInfo', "p2p_address physical_cpu virt_cpu version buffer_size "
                "build_date version_string")):
    """Information returned about a core by sver.

    Parameters
    ----------
    p2p_address : (x, y)
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


class IPTag(collections.namedtuple("IPTag",
                                   "addr max port timeout flags count rx_port "
                                   "spin_addr spin_port")):
    """An IPTag as read from a SpiNNaker machine."""
    @classmethod
    def from_bytestring(cls, bytestring):
        (ip, max, port, timeout, flags, count, rx_port, spin_addr,
         spin_port) = struct.unpack("<4s 6s 3H I 2H B", bytestring[:25])
        # Convert the IP address into a string, otherwise save
        ip_addr = '.'.join(str(x) for x in struct.unpack("4B", ip))

        return cls(ip_addr, max, port, timeout, flags, count, rx_port,
                   spin_addr, spin_port)


# Dictionary of (address % 4, n_bytes % 4) to data type
address_length_dtype = {
    (i, j): (DataType.word if (i == j == 0) else
             (DataType.short if (i % 2 == j % 2 == 0) else
              DataType.byte))
    for i in range(4) for j in range(4)
}


class SpiNNakerMemoryError(Exception):
    """Raised when it is not possible to allocate memory on a SpiNNaker
    chip.
    """
    def __init__(self, size, x, y):
        self.size = size
        self.chip = (x, y)

    def __str__(self):
        return ("Failed to allocate {} bytes of SDRAM on chip ({}, {})".
                format(self.size, self.chip[0], self.chip[1]))


class MemoryIO(object):
    def __init__(self, machine_controller, x, y, start_address, end_address):
        """Create a file-like view onto a subset of the memory-space of a chip.

        Parameters
        ----------
        machine_controller : :py:class:`~MachineController`
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
        """
        # Store parameters
        self._x = x
        self._y = y
        self._machine_controller = machine_controller
        self._start_address = start_address
        self._end_address = end_address

        # Current offset from start address
        self._offset = 0

    def read(self, n_bytes):
        """Read a number of bytes from the SDRAM.

        Parameters
        ----------
        n_bytes : int
            A number of bytes to read.

        .. note::
            Reads beyond the specified memory range will be truncated.

        Returns
        -------
        :py:class:`bytes`
            Data read from SpiNNaker as a bytestring.
        """
        # Determine how far to read, then read nothing beyond that point.
        if self.address + n_bytes > self._end_address:
            n_bytes = min(n_bytes, self._end_address - self.address)

            if n_bytes <= 0:
                return b''

        # Perform the read and increment the offset
        data = self._machine_controller.read(
            self._x, self._y, 0, self.address, n_bytes)
        self._offset += n_bytes
        return data

    def write(self, bytes):
        """Write data to the SDRAM.

        Parameters
        ----------
        bytes : :py:class:`bytes`
            Data to write to the SDRAM as a bytestring.

        .. note::
            Writes beyond the specified memory range will be truncated.

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
        self._machine_controller.write(
            self._x, self._y, 0, self.address, bytes)
        self._offset += len(bytes)
        return len(bytes)

    def tell(self):
        """Get the current offset in the memory region.

        Returns
        -------
        int
            Current offset (starting at 0).
        """
        return self._offset

    @property
    def address(self):
        """Get the current address (indexed from 0x00000000)."""
        return self._offset + self._start_address

    def seek(self, n_bytes):
        """Seek to a new position in the memory region."""
        self._offset += n_bytes
