from rig.machine_control.packets import SDPPacket, SCPPacket


class TestSDPPacket(object):
    """Test SDPPacket representations."""
    def test_from_bytestring_to_bytestring(self):
        """Test creating a new SDPPacket from a bytestring."""
        # Create bytestring representing a packet with:
        #     flags: 0x87
        #     tag: 0xF0
        #     dest_port: 7 (max 3 bits)
        #     dest_cpu: 0x0F (max 5 bits)
        #     src_port: 7
        #     src_cpu: 0x0E
        #     dest_x: 0xA5
        #     dest_y: 0x5A
        #     src_x: 0x0F
        #     src_y: 0xF0
        #     data: 0xDEADBEEF
        packet = b'\x00\x00\x87\xf0\xef\xee\x5a\xa5\xf0\x0f\xDE\xAD\xBE\xEF'
        sdp_packet = SDPPacket.from_bytestring(packet)

        assert isinstance(sdp_packet, SDPPacket)
        assert sdp_packet.reply_expected
        assert sdp_packet.tag == 0xF0
        assert sdp_packet.dest_port == 7
        assert sdp_packet.dest_cpu == 0x0F
        assert sdp_packet.src_port == 7
        assert sdp_packet.src_cpu == 0x0E
        assert sdp_packet.dest_x == 0xA5
        assert sdp_packet.dest_y == 0x5A
        assert sdp_packet.src_x == 0x0F
        assert sdp_packet.src_y == 0xF0
        assert sdp_packet.data == b'\xDE\xAD\xBE\xEF'

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert sdp_packet.bytestring == packet

    def test_from_bytestring_no_reply(self):
        """Test creating a new SDPPacket from a bytestring."""
        # Create bytestring representing a packet with:
        #     flags: 0x07
        packet = b'\x00\x00\x07\xf0\xef\xee\xa5\x5a\x0f\xf0\xDE\xAD\xBE\xEF'
        sdp_packet = SDPPacket.from_bytestring(packet)

        assert isinstance(sdp_packet, SDPPacket)
        assert not sdp_packet.reply_expected


class TestSCPPacket(object):
    """Test packets conforming to the SCP protocol."""
    def test_from_bytestring_short(self):
        """Test creating an SCP Packet from a bytestring when the SCP Packet is
        short (no arguments, no data).
        """
        # Create bytestring representing a packet with:
        #     flags: 0x87
        #     tag: 0xF0
        #     dest_port: 7 (max 3 bits)
        #     dest_cpu: 0x0F (max 5 bits)
        #     src_port: 7
        #     src_cpu: 0x0E
        #     dest_x: 0xA5
        #     dest_y: 0x5A
        #     src_x: 0x0F
        #     src_y: 0xF0
        #     cmd_rc: 0xDEAD
        #     seq: 0xBEEF
        packet = b'\x00\x00\x87\xf0\xef\xee\x5a\xa5\xf0\x0f\xAD\xDE\xEF\xBE'
        scp_packet = SCPPacket.from_bytestring(packet)

        assert isinstance(scp_packet, SCPPacket)
        assert scp_packet.reply_expected
        assert scp_packet.tag == 0xF0
        assert scp_packet.dest_port == 7
        assert scp_packet.dest_cpu == 0x0F
        assert scp_packet.src_port == 7
        assert scp_packet.src_cpu == 0x0E
        assert scp_packet.dest_x == 0xA5
        assert scp_packet.dest_y == 0x5A
        assert scp_packet.src_x == 0x0F
        assert scp_packet.src_y == 0xF0
        assert scp_packet.cmd_rc == 0xDEAD
        assert scp_packet.seq == 0xBEEF
        assert scp_packet.arg1 is None
        assert scp_packet.arg2 is None
        assert scp_packet.arg3 is None
        assert scp_packet.data == b''

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_from_bytestring(self):
        """Test creating a new SCPPacket from a bytestring."""
        # Create bytestring representing a packet with:
        #     flags: 0x87
        #     tag: 0xF0
        #     dest_port: 7 (max 3 bits)
        #     dest_cpu: 0x0F (max 5 bits)
        #     src_port: 7
        #     src_cpu: 0x0E
        #     dest_x: 0xA5
        #     dest_y: 0x5A
        #     src_x: 0x0F
        #     src_y: 0xF0
        #     cmd_rc: 0xDEAD
        #     seq: 0xBEEF
        #     arg1: 0xA5A5B7B7
        #     arg2: 0xCAFECAFE
        #     arg3: 0x5A5A7B7B
        #     data: 0xFEEDDEAF01
        packet = b'\x00\x00' + \
                 b'\x87\xf0\xef\xee\x5a\xa5\xf0\x0f\xAD\xDE\xEF\xBE' + \
                 b'\xB7\xB7\xA5\xA5\xFE\xCA\xFE\xCA\x7B\x7B\x5A\x5A' + \
                 b'\xFE\xED\xDE\xAF\x01'
        scp_packet = SCPPacket.from_bytestring(packet)

        assert isinstance(scp_packet, SCPPacket)
        assert scp_packet.reply_expected
        assert scp_packet.tag == 0xF0
        assert scp_packet.dest_port == 7
        assert scp_packet.dest_cpu == 0x0F
        assert scp_packet.src_port == 7
        assert scp_packet.src_cpu == 0x0E
        assert scp_packet.dest_x == 0xA5
        assert scp_packet.dest_y == 0x5A
        assert scp_packet.src_x == 0x0F
        assert scp_packet.src_y == 0xF0
        assert scp_packet.cmd_rc == 0xDEAD
        assert scp_packet.seq == 0xBEEF
        assert scp_packet.arg1 == 0xA5A5B7B7
        assert scp_packet.arg2 == 0xCAFECAFE
        assert scp_packet.arg3 == 0x5A5A7B7B
        assert scp_packet.data == b'\xFE\xED\xDE\xAF\x01'

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_from_bytestring_0_args(self):
        """Test creating a new SCPPacket from a bytestring."""
        # Create bytestring representing a packet with:
        #     flags: 0x87
        #     tag: 0xF0
        #     dest_port: 7 (max 3 bits)
        #     dest_cpu: 0x0F (max 5 bits)
        #     src_port: 7
        #     src_cpu: 0x0E
        #     dest_x: 0xA5
        #     dest_y: 0x5A
        #     src_x: 0x0F
        #     src_y: 0xF0
        #     cmd_rc: 0xDEAD
        #     seq: 0xBEEF
        #     data: 0xA5A5B7B7CAFECAFE5A5A7B7BFEEDDEAF01
        packet = b'\x00\x00' + \
                 b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
                 b'\xB7\xB7\xA5\xA5\xFE\xCA\xFE\xCA\x7B\x7B\x5A\x5A' + \
                 b'\xFE\xED\xDE\xAF\x01'
        scp_packet = SCPPacket.from_bytestring(packet, n_args=0)

        assert scp_packet.cmd_rc == 0xDEAD
        assert scp_packet.seq == 0xBEEF
        assert scp_packet.arg1 is None
        assert scp_packet.arg2 is None
        assert scp_packet.arg3 is None
        assert scp_packet.data == \
            b'\xB7\xB7\xA5\xA5\xFE\xCA\xFE\xCA\x7B\x7B\x5A\x5A' + \
            b'\xFE\xED\xDE\xAF\x01'

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_from_bytestring_0_args_short(self):
        """Test creating a new SCPPacket from a bytestring."""
        packet = b'\x00\x00\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE'
        scp_packet = SCPPacket.from_bytestring(packet)

        assert scp_packet.arg1 is None
        assert scp_packet.arg2 is None
        assert scp_packet.arg3 is None
        assert scp_packet.data == b''

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_from_bytestring_1_args(self):
        """Test creating a new SCPPacket from a bytestring."""
        #     arg1: 0xA5A5B7B7
        #     data: 0xCAFECAFE5A5A7B7BFEEDDEAF01
        packet = b'\x00\x00' + \
                 b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
                 b'\xB7\xB7\xA5\xA5\xFE\xCA\xFE\xCA\x7B\x7B\x5A\x5A' + \
                 b'\xFE\xED\xDE\xAF\x01'
        scp_packet = SCPPacket.from_bytestring(packet, n_args=1)

        assert scp_packet.arg1 == 0xA5A5B7B7
        assert scp_packet.arg2 is None
        assert scp_packet.arg3 is None
        assert scp_packet.data == \
            b'\xFE\xCA\xFE\xCA\x7B\x7B\x5A\x5A' + \
            b'\xFE\xED\xDE\xAF\x01'

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_from_bytestring_1_args_short(self):
        """Test creating a new SCPPacket from a bytestring."""
        #     arg1: 0xA5A5B7B7
        packet = b'\x00\x00' + \
                 b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
                 b'\xB7\xB7\xA5\xA5'
        scp_packet = SCPPacket.from_bytestring(packet)

        assert scp_packet.arg1 == 0xA5A5B7B7
        assert scp_packet.arg2 is None
        assert scp_packet.arg3 is None
        assert scp_packet.data == b''

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_from_bytestring_2_args(self):
        """Test creating a new SCPPacket from a bytestring."""
        #     arg1: 0xA5A5B7B7
        #     arg2: 0xCAFECAFE
        #     data: 0x5A5A7B7BFEEDDEAF01
        packet = b'\x00\x00' + \
                 b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
                 b'\xB7\xB7\xA5\xA5\xFE\xCA\xFE\xCA\x7B\x7B\x5A\x5A' + \
                 b'\xFE\xED\xDE\xAF\x01'
        scp_packet = SCPPacket.from_bytestring(packet, n_args=2)

        assert scp_packet.arg1 == 0xA5A5B7B7
        assert scp_packet.arg2 == 0xCAFECAFE
        assert scp_packet.arg3 is None
        assert scp_packet.data == b'\x7B\x7B\x5A\x5A\xFE\xED\xDE\xAF\x01'

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_from_bytestring_2_args_short(self):
        """Test creating a new SCPPacket from a bytestring."""
        #     arg1: 0xA5A5B7B7
        #     arg2: 0xCAFECAFE
        packet = b'\x00\x00' + \
                 b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
                 b'\xB7\xB7\xA5\xA5\xFE\xCA\xFE\xCA'
        scp_packet = SCPPacket.from_bytestring(packet)

        assert scp_packet.arg1 == 0xA5A5B7B7
        assert scp_packet.arg2 == 0xCAFECAFE
        assert scp_packet.arg3 is None
        assert scp_packet.data == b''

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet
