"""A stop-and-wait blocking implementation of the SCP protocol.
"""
import collections
import enum
import socket
import struct
from . import packets


CoreInfo = collections.namedtuple(
    'CoreInfo', "p2p_address physical_cpu virt_cpu version "
                "buffer_size build_date version_string")


class LEDAction(enum.IntEnum):
    ON = 3
    OFF = 2
    TOGGLE = 1


class DataType(enum.IntEnum):
    """Data size types."""
    BYTE = 0
    SHORT = 1
    WORD = 2


class SCPCommands(enum.IntEnum):
    SVER = 0
    READ = 2
    WRITE = 3
    LED = 25
    IPTAG = 26


class IPTagCommands(enum.IntEnum):
    SET = 1
    GET = 2
    CLEAR = 3


class SCPCommunicator(object):
    """Implements the SCP protocol for communicating with a SpiNNaker machine.
    """
    error_codes = {}

    def __init__(self, spinnaker_host, n_tries=5, timeout=0.5):
        """Create a new communicator to handle control of the given SpiNNaker
        host.

        Parameters
        ----------
        spinnaker_host : str
            A IP address or hostname of the SpiNNaker machine to control.
        n_tries : int
            The maximum number of tries to communicate with the machine before
            failing.
        timeout : float
            The timeout to use on the socket.
        """
        # Create a socket to communicate with the SpiNNaker machine
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self.sock.connect((spinnaker_host, 17893))

        # Store the number of tries that will be allowed
        self.n_tries = n_tries

        # The current seq value
        self._seq = 0

    @classmethod
    def _register_error(cls, cmd_rc):
        """Register an Exception class as belonging to a certain CMD_RC value.
        """
        def err_(err):
            cls.error_codes[cmd_rc] = err
            return err
        return err_

    def _send_scp(self, x, y, p, cmd, arg1=0, arg2=0, arg3=0, data=b'',
                  expected_args=3):
        """Transmit a packet to the SpiNNaker machine and block until an
        acknowledgement is received.

        Parameters
        ----------
        x : int
        y : int
        p : int
        cmd : int
        arg1 : int
        arg2 : int
        arg3 : int
        data : bytestring
        expected_args : int
            The number of arguments (0-3) that are expected in the returned
            packet.

        Returns
        -------
        :py:class:`~rig.communicator.SCPPacket`
            The packet that was received in acknowledgement of the transmitted
            packet.
        """
        # Construct the packet that will be sent
        packet = packets.SCPPacket(
            reply_expected=True, tag=0xff, dest_port=0, dest_cpu=p,
            src_port=7, src_cpu=31, dest_x=x, dest_y=y, src_x=0, src_y=0,
            cmd_rc=cmd, seq=self._seq, arg1=arg1, arg2=arg2, arg3=arg3,
            data=data
        )

        # Repeat until a reply is received or we run out of tries.
        n_tries = 0
        while n_tries < self.n_tries:
            # Transit the packet
            self.sock.send(b'\x00\x00' + packet.bytestring)
            n_tries += 1

            try:
                # Try to receive the returned acknowledgement
                ack = self.sock.recv(512)
            except IOError:
                # There was nothing to receive from the socket
                continue

            # Convert the possible returned packet into a SDPPacket and hence
            # to an SCPPacket.  If the seq field matches the expected seq then
            # the acknowledgement has been returned.
            # Unsure about the padding here
            scp = packets.SCPPacket.from_bytestring(ack[2:],
                                                    n_args=expected_args)

            # Check that the CMD_RC isn't an error
            if scp.cmd_rc in self.error_codes:
                raise self.error_codes[scp.cmd_rc](
                    "Packet with arguments: cmd={}, arg1={}, arg2={}, arg3={};"
                    " sent to core ({},{},{}) was bad.".format(
                        cmd, arg1, arg2, arg3, x, y, p
                    )
                )

            if scp.seq == self._seq:
                # The packet is the acknowledgement.  Increment the sequence
                # indicator and return the packet.
                self._seq ^= 1
                return scp

        # The packet we transmitted wasn't acknowledged.
        raise TimeoutError(
            "Exceeded {} tries when trying to transmit packet.".format(
                self.n_tries)
        )

    def software_version(self, x, y, p):
        """Get the software version for a given SpiNNaker core.
        """
        sver = self._send_scp(x, y, p, SCPCommands.SVER)

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

    def set_led(self, x, y, led, action=LEDAction.ON):
        """Set the state of an LED.

        Parameters
        ----------
        led : int
            Number of the LED to set the state of (0-3)
        action : LEDAction
            Action to take with the LED (on/off/toggle)
        """
        arg1 = int(action) << (led * 2)
        self._send_scp(x, y, 0, SCPCommands.LED, arg1=arg1, expected_args=0)

    def read(self, x, y, p, address, length_bytes, data_type=DataType.BYTE):
        """Read a bytestring from an address in memory.

        Parameters
        ----------
        address : int
            The address at which to start reading the data.
        length_bytes : int
            The number of bytes to read from memory.
        data_type : DataType
            The size of the data to write into memory.

        Returns
        -------
        bytestring
            The data is read back from memory as a bytestring.
        """
        read_scp = self._send_scp(x, y, p, SCPCommands.READ, address,
                                  length_bytes, int(data_type),
                                  expected_args=0)
        return read_scp.data

    def write(self, x, y, p, address, data, data_type=DataType.BYTE):
        """Write a bytestring to an address in memory.

        Parameters
        ----------
        address : int
            The address at which to start writing the data.
        data : bytestring
            Data to write into memory.
        data_type : :py:class:`.DataType`
            The size of the data to write into memory.
        """
        length_bytes = len(data)
        self._send_scp(x, y, p, SCPCommands.WRITE, address, length_bytes,
                       int(data_type), data, expected_args=0)

    def iptag_set(self, x, y, iptag, addr, port):
        """Set the value of an IPTag.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to set
        """
        # Format the IP address
        ip_addr = struct.pack('!4B',
                              *map(int, socket.gethostbyname(addr).split('.')))
        self._send_scp(x, y, 0, SCPCommands.IPTAG,
                       int(IPTagCommands.SET) << 16 | iptag,
                       port, struct.unpack('<I', ip_addr)[0])

    def iptag_get(self, x, y, iptag):
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
        ack = self._send_scp(x, y, 0, SCPCommands.IPTAG,
                             int(IPTagCommands.GET) << 16 | iptag, 1,
                             expected_args=0)
        return IPTag.from_bytestring(ack.data)

    def iptag_clear(self, x, y, iptag):
        """Clear an IPTag.

        Parameters
        ----------
        iptag : int
            Index of the IPTag to clear.
        """
        self._send_scp(x, y, 0, SCPCommands.IPTAG,
                       int(IPTagCommands.CLEAR) << 16 | iptag)


class SDRAMFile(object):
    def __init__(self, communicator, x, y,
                 start_address=0x70000000,
                 end_address=0x7fffffff):
        """Create a file-like view onto the SDRAM of a chip.

        Parameters
        ----------
        communicator : :py:class:`.SCPCommunicator`
            A communicator to handle transmitting and receiving packets from
            the SpiNNaker machine.
        x : int
            The x co-ordinate of the chip to represent the SDRAM of.
        y : int
            The y co-ordinate of the chip to represent the SDRAM of.
        start_address : int
            Starting address of the SDRAM.
        end_address : int
            End address of the SDRAM.
        """
        # Store parameters
        self._x = x
        self._y = y
        self._communicator = communicator
        self._start_address = start_address
        self._end_address = end_address

        # Current offset from start address
        self._offset = 0

    @staticmethod
    def _get_data_type_from_offset_and_size(address, n_bytes):
        """Get the best data type to use based on an address and a number of
        bytes.
        """
        # Map of length & 0x3 => address & 0x3 => DataType
        data_types = {
            1: {n: DataType.BYTE for n in range(4)},
            2: {n: DataType.BYTE if (n & 1) == 1 else DataType.SHORT
                for n in range(4)},
            3: {n: DataType.BYTE for n in range(4)},
            0: {
                0: DataType.WORD,
                1: DataType.BYTE,
                2: DataType.SHORT,
                3: DataType.BYTE,
            }
        }
        return data_types[n_bytes & 0x3][address & 0x3]

    def read(self, n_bytes):
        """Read a number of bytes from the SDRAM.

        Parameters
        ----------
        n_bytes : int
            A number of bytes to read.

        Returns
        -------
        bytestring
            Data read from SpiNNaker as a bytestring.
        """
        # Make as many calls as must be made
        data = b''
        while n_bytes > 0 and self.address <= self._end_address:
            # Get the number of bytes we can actually read
            _n_bytes = min((256, n_bytes,
                            self._end_address - self.address + 1))

            # Determine the data type
            data_type = self._get_data_type_from_offset_and_size(self.address,
                                                                 _n_bytes)

            # Get the data
            data += self._communicator.read(self._x, self._y, 0, self.address,
                                            _n_bytes, data_type)

            # Progress the pointer and decrease the count
            self.seek(_n_bytes)
            n_bytes -= _n_bytes

        # Return the data as read
        return data

    def write(self, bytes):
        """Write data to the SDRAM.

        Parameters
        ----------
        bytes : bytestring
            Data to write to the SDRAM as a bytestring.
        """
        # Check that this will not go beyond the end of the SDRAM
        if self.address + len(bytes) > self._end_address:
            raise EOFError(
                "Writing {} bytes would go beyond the range of SDRAM.".format(
                    len(bytes)))

        # Determine the data type
        data_type = self._get_data_type_from_offset_and_size(self.address,
                                                             len(bytes))

        # Make as many calls as must be made
        while len(bytes) > 0:
            address = self._start_address + self._offset
            self._communicator.write(self._x, self._y, 0, address,
                                     bytes[:256], data_type)

            self.seek(len(bytes[:256]))
            bytes = bytes[256:]

    def tell(self):
        """Get the current offset in SDRAM.

        Returns
        -------
        int
            The current offset from SDRAM (starting at 0).
        """
        return self._offset

    @property
    def address(self):
        """Get the current address (indexed from 0x00000000)."""
        return self._offset + self._start_address

    def seek(self, n_bytes):
        """Seek to a new position in the file."""
        self._offset += n_bytes


class SCPError(IOError):
    """Base Error for SCP return codes."""
    pass


class TimeoutError(SCPError):
    """Raised when an SCP is not acknowledged within the given period of time.
    """
    pass


@SCPCommunicator._register_error(0x81)
class BadPacketLengthError(SCPError):
    """Raised when an SCP packet is an incorrect length."""
    pass


@SCPCommunicator._register_error(0x83)
class InvalidCommandError(SCPError):
    """Raised when an SCP packet contains an invalid command code."""
    pass


@SCPCommunicator._register_error(0x84)
class InvalidArgsError(SCPError):
    """Raised when an SCP packet has an invalid argument."""
    pass


class IPTag(collections.namedtuple("IPTag",
                                   "addr max port timeout flags count rx_port "
                                   "spin_addr spin_port")):
    """An IPTag as read from a SpiNNaker machine."""
    @classmethod
    def from_bytestring(cls, bytestring):
        (ip, max, port, timeout, flags, count, rx_port, spin_addr,
         spin_port) = struct.unpack("4s 6s 3H I 2H B", bytestring[:25])
        # Convert the IP address into a string, otherwise save
        ip_addr = '.'.join(str(x) for x in struct.unpack("4B", ip))

        return cls(ip_addr, max, port, timeout, flags, count, rx_port,
                   spin_addr, spin_port)
