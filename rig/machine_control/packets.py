"""Representations of SDP and SCP Packets."""
import struct

# SDP header flags
FLAG_REPLY = 0x87
FLAG_NO_REPLY = 0x07


class SDPPacket(object):
    """An SDP Packet"""
    __slots__ = ["reply_expected", "tag", "dest_port", "dest_cpu", "src_port",
                 "src_cpu", "dest_x", "dest_y", "src_x", "src_y", "data"]

    def __init__(self, reply_expected=False, tag=0xff,
                 dest_port=None, dest_cpu=None, src_port=7, src_cpu=31,
                 dest_x=None, dest_y=None, src_x=0, src_y=0, data=b''):
        """Create a new SDPPacket.

        Parameters
        ----------
        dest_x : int (0-255)
            x co-ordinate of the chip to which the packet should be sent.
        dest_y : int (0-255)
            y co-ordinate of the chip to which the packet should be sent.
        dest_cpu : int (0-17)
            Index of the core which should receive the packet.
        dest_port : int (0-7)
            Port which should receive the packet (0 is reserved for debugging).
        data : bytes
            Data to append to the packet.
        reply_expected : bool
            True if a response to this packet is expected, if False (the
            default) no response is expected.

        Other Parameters
        ----------------
        tag : int
            IPTag used to determine where to send packets over IPv4. The
            default (``0xff``) indicates a packet being transmitted into
            SpiNNaker.
        src_port : int
            Source port of the packet.
        src_cpu : int
            Source CPU of the packet.
        src_x : int
            Source x co-ordinate of the packet.
        src_y : int
            Source y co-ordinate of the packet.

        .. note::
            The default values for `tag`, `src_port`, `src_cpu`, `src_x` and
            `src_y` indicate a packet being transmitted to SpiNNaker over the
            network and will not require changing for this use.
        """
        self.reply_expected = reply_expected
        self.tag = tag
        self.dest_port = dest_port
        self.dest_cpu = dest_cpu
        self.src_port = src_port
        self.src_cpu = src_cpu
        self.dest_x = dest_x
        self.dest_y = dest_y
        self.src_x = src_x
        self.src_y = src_y
        self.data = data

    @classmethod
    def from_bytestring(cls, bytestring):
        """Create a new SDPPacket from a bytestring.

        Returns
        -------
        SDPPacket
            An SDPPacket containing the data from the bytestring.
        """
        packet = cls()
        _unpack_sdp_into_packet(packet, bytestring)
        return packet

    @property
    def packed_data(self):
        return self.data

    @property
    def bytestring(self):
        """Convert the packet into a bytestring."""
        # Construct the header
        return struct.pack(
            '<2x8B',
            FLAG_REPLY if self.reply_expected else FLAG_NO_REPLY,
            self.tag,
            (self.dest_port & 0x7) << 5 | (self.dest_cpu & 0x1f),
            (self.src_port & 0x7) << 5 | (self.src_cpu & 0x1f),
            self.dest_y,
            self.dest_x,
            self.src_y,
            self.src_x
        ) + self.packed_data


class SCPPacket(SDPPacket):
    """An SCP Packet"""
    __slots__ = ["cmd_rc", "seq", "arg1", "arg2", "arg3"]

    def __init__(self, reply_expected=False, tag=0xff,
                 dest_port=None, dest_cpu=None, src_port=7, src_cpu=31,
                 dest_x=None, dest_y=None, src_x=0, src_y=0, cmd_rc=None,
                 seq=0, arg1=None, arg2=None, arg3=None, data=b''):
        """Create a new SCP formatted packet.

        Parameters
        ----------
        dest_x : int (0-255)
            x co-ordinate of the chip to which the packet should be sent.
        dest_y : int (0-255)
            y co-ordinate of the chip to which the packet should be sent.
        dest_cpu : int (0-17)
            Index of the core which should receive the packet.
        dest_port : int (0-7)
            Port which should receive the packet (0 is reserved for debugging).
        cmd_rc : int (1 word)
            Command/return code of the packet. This will determine what action
            occurs if the packet is handled by SARK or SCAMP.
        arg1 : int (1 word) or None
            If None then ignored.
        arg2 : int (1 word) or None
            If None then ignored.
        arg3 : int (1 word) or None
            If None then ignored.
        data : bytes
            Data to append to the packet after `arg1`, `arg2` and `arg3`.
        reply_expected : bool
            True if a response to this packet is expected, if False (the
            default) no response is expected.

        Other Parameters
        ----------------
        tag : int
            IPTag used to determine where to send packets over IPv4. The
            default (``0xff``) indicates a packet being transmitted into
            SpiNNaker.
        src_port : int
            Source port of the packet.
        src_cpu : int
            Source CPU of the packet.
        src_x : int
            Source x co-ordinate of the packet.
        src_y : int
            Source y co-ordinate of the packet.
        seq : int
            Sequence number of the packet, used when communicating the SCAMP or
            SARK.

        .. note::
            The default values for `tag`, `src_port`, `src_cpu`, `src_x` and
            `src_y` indicate a packet being transmitted to SpiNNaker over the
            network and will not require changing for this use.
        """
        super(SCPPacket, self).__init__(
            reply_expected, tag, dest_port, dest_cpu, src_port,
            src_cpu, dest_x, dest_y, src_x, src_y, data)

        # Store additional data for the SCP packet
        self.cmd_rc = cmd_rc
        self.seq = seq
        self.arg1 = arg1
        self.arg2 = arg2
        self.arg3 = arg3

    @classmethod
    def from_bytestring(cls, scp_packet, n_args=3):
        """Create a new SCPPacket from a bytestring.

        Parameters
        ----------
        scp_packet : bytestring
            Bytestring containing an SCP packet.
        n_args : int
            The number of arguments to unpack from the SCP data.
        """
        packet = cls()  # Empty packet
        _unpack_sdp_into_packet(packet, scp_packet)

        # Unpack the SCP header from the data
        data = packet.data[4:]
        packet.cmd_rc, packet.seq = struct.unpack_from('<2H', packet.data)

        # Unpack as much of the data as is present
        data_len = len(data)
        offset = 0
        if n_args >= 1 and data_len >= 4:
            packet.arg1, = struct.unpack_from('<I', data, offset)
            offset += 4

            if n_args >= 2 and data_len >= 8:
                packet.arg2, = struct.unpack_from('<I', data, offset)
                offset += 4

                if n_args >= 3 and data_len >= 12:
                    packet.arg3, = struct.unpack_from('<I', data, offset)
                    offset += 4

        packet.data = data[offset:]

        return packet

    @property
    def packed_data(self):
        """Pack the data for the SCP packet."""
        # Pack the header
        scp_header = struct.pack("<2H", self.cmd_rc, self.seq)

        # Potential loop intentionally unrolled
        if self.arg1 is not None:
            scp_header += struct.pack('<I', self.arg1)
        if self.arg2 is not None:
            scp_header += struct.pack('<I', self.arg2)
        if self.arg3 is not None:
            scp_header += struct.pack('<I', self.arg3)

        # Return the SCP header and the rest of the data
        return scp_header + self.data

    def __repr__(self):
        """Produce a human-readable summary of (the most important parts of)
        the packet.
        """
        return ("<{} x: {}, y: {}, cpu: {}, "
                "cmd_rc: {}, arg1: {}, arg2: {}, arg3: {}, "
                "data: {}>".format(self.__class__.__name__,
                                   self.dest_x, self.dest_y, self.dest_cpu,
                                   self.cmd_rc,
                                   self.arg1, self.arg2, self.arg3,
                                   repr(self.data)))


def _unpack_sdp_into_packet(packet, bytestring):
    """Unpack the SDP header from a bytestring into a packet.

    Parameters
    ----------
    packet : :py:class:`.SDPPacket`
        Packet into which to store the unpacked header.
    bytestring : bytes
        Bytes from which to unpack the header data.
    """
    # Extract the header and the data from the packet
    packet.data = bytestring[10:]  # Everything but the header

    # Unpack the header
    (flags, packet.tag, dest_cpu_port, src_cpu_port,
     packet.dest_y, packet.dest_x,
     packet.src_y, packet.src_x) = struct.unpack_from('<2x8B', bytestring)
    packet.reply_expected = flags == FLAG_REPLY

    # Neaten up the combined VCPU and port fields
    packet.dest_cpu = dest_cpu_port & 0x1f
    packet.dest_port = (dest_cpu_port >> 5)  # & 0x07
    packet.src_cpu = src_cpu_port & 0x1f
    packet.src_port = (src_cpu_port >> 5)  # & 0x07
