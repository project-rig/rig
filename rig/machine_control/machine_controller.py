import collections
import socket
import struct

from .consts import SCPCommands, DataType
from . import boot, consts
from .scp_connection import SCPConnection
from rig.utils.contexts import ContextMixin, Required


class MachineController(ContextMixin):
    """TODO

    Attributes
    ----------
    """
    def __init__(self, initial_host, n_tries=5, timeout=0.5,
                 initial_context={"app_id": 30}):
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

    def send_scp(self, x, y, *args, **kwargs):
        """Determine the best connection to use to send an SCP packet and use
        it to transmit.

        See the arguments for
        :py:method:`~rig.machine_controller.scp_connection.SCPConnection` for
        details.
        """
        return self.connections[0].send_scp(x, y, *args, **kwargs)

    def boot(self, width, height, **boot_kwargs):
        """Boot a SpiNNaker machine of the given size.

        Parameters
        ----------
        width : int
            Width of the machine (0 < w < 256)
        height : int
            Height of the machine (0 < h < 256)

        For further boot arguments see
        :py:func:`~rig.machine_controller.boot.boot`.

        Notes
        -----
        The constants `rig.machine_control.boot.spinX_boot_options` can be used
        to specify boot parameters, for example::

            controller.boot(**spin5_boot_options)

        Will boot the Spin5 board connected to by `controller`.
        """
        boot.boot(self.initial_host, width=width, height=height, **boot_kwargs)

    @ContextMixin.use_contextual_arguments
    def get_software_version(self, x=Required, y=Required, processor=0):
        """Get the software version for a given SpiNNaker core.

        Returns
        -------
        :py:class:`CoreInfo`
            Information about the software running on a core.
        """
        sver = self.send_scp(x, y, processor, SCPCommands.sver)

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
            block, data = data[:256], data[256:]
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
        data_type : :py:class:`~rig.machine_controller.consts.DataType`
            The size of the data to write into memory.
        """
        length_bytes = len(data)
        self.send_scp(x, y, p, SCPCommands.write, address, length_bytes,
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
            reads = min(256, length_bytes - len(data))

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
            The number of bytes to read from memory, must be <= 256.
        data_type : DataType
            The size of the data to write into memory.

        Returns
        -------
        :py:class:`bytes`
            The data is read back from memory as a bytestring.
        """
        read_scp = self.send_scp(x, y, p, SCPCommands.read, address,
                                 length_bytes, int(data_type),
                                 expected_args=0)
        return read_scp.data

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
        self.send_scp(x, y, 0, SCPCommands.iptag,
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
        ack = self.send_scp(x, y, 0, SCPCommands.iptag,
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
        self.send_scp(x, y, 0, SCPCommands.iptag,
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
        self.send_scp(x, y, 0, SCPCommands.led, arg1=arg1, expected_args=0)

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
        rv = self.send_scp(x, y, 0, SCPCommands.alloc_free, arg1, size, tag)
        if rv.arg1 == 0:
            # Allocation failed
            raise SpiNNakerMemoryError(size, x, y)
        return rv.arg1


class CoreInfo(collections.namedtuple(
    'CoreInfo', "p2p_address physical_cpu virt_cpu version buffer_size "
                "build_date version_string")):
    """Information returned about a core by sver.

    Paramters
    ---------
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
              DataType.byte)) for i in range(4) for j in range(4)
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
