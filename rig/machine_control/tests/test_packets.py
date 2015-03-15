import pytest
from ..packets import SDPPacket, SCPPacket
from .. import packets


class TestRangedIntAttribute(object):
    def test_min_exclusive(self):
        # Test values are correctly checked in the min value is excluded from
        # the valid range.
        class X(object):
            y = packets.RangedIntAttribute(0, 10, min_inclusive=False)

        x = X()
        with pytest.raises(ValueError):
            x.y = 0

        x.y = 1

    def test_max_inclusive(self):
        # Test values are correctly checked in the max value is included in the
        # valid range.
        class X(object):
            y = packets.RangedIntAttribute(0, 10, max_inclusive=True)

        x = X()
        x.y = 10

    def test_min_max_fail(self):
        # Test that a value error is raised on instantiation if the min/max
        # values are wrong.
        with pytest.raises(ValueError):
            class X(object):
                y = packets.RangedIntAttribute(100, 0)

    def test_type_fail(self):
        class X(object):
            y = packets.RangedIntAttribute(0, 100)

        x = X()
        with pytest.raises(TypeError):
            x.y = "Oops!"

    def test_allow_none(self):
        class X(object):
            y = packets.RangedIntAttribute(0, 10, allow_none=False)

        x = X()
        with pytest.raises(ValueError):
            x.y = None

        class Y(object):
            y = packets.RangedIntAttribute(0, 10, allow_none=True)

        y = Y()
        y.y = None


class TestByteStringAttribute(object):
    def test_unlimited_length(self):
        class X(object):
            y = packets.ByteStringAttribute(default=b"default")

        x = X()

        assert x.y == b"default"

        x.y = b""
        assert x.y == b""

        x.y = b"hello"
        assert x.y == b"hello"

        x.y = b"01234567"
        assert x.y == b"01234567"

    def test_max_length(self):
        class X(object):
            y = packets.ByteStringAttribute(max_length=8)

        x = X()

        assert x.y == b""

        x.y = b""
        assert x.y == b""

        x.y = b"hello"
        assert x.y == b"hello"

        x.y = b"01234567"
        assert x.y == b"01234567"

        with pytest.raises(ValueError):
            x.y = b"012345678"


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
        packet = b'\x87\xf0\xef\xee\x5a\xa5\xf0\x0f\xDE\xAD\xBE\xEF'
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
        packet = b'\x07\xf0\xef\xee\xa5\x5a\x0f\xf0\xDE\xAD\xBE\xEF'
        sdp_packet = SDPPacket.from_bytestring(packet)

        assert isinstance(sdp_packet, SDPPacket)
        assert not sdp_packet.reply_expected

    def test_values(self):
        """Check that errors are raised when values are out of range."""
        with pytest.raises(TypeError):  # Ints should be ints
            SDPPacket(False, 3.0, 0, 0, 0, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # IPTag is 8 bits
            SDPPacket(False, 300, 0, 0, 0, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # IPTag is 8 bits
            SDPPacket(False, -1, 0, 0, 0, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_port is 3 bits
            SDPPacket(False, 255, 8, 0, 0, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_port is 3 bits
            SDPPacket(False, 255, -1, 0, 0, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_cpu is 5 bits but should range 0..17
            SDPPacket(False, 255, 7, 18, 0, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_cpu is 5 bits but should range 0..17
            SDPPacket(False, 255, 7, -1, 0, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # src_port is 3 bits
            SDPPacket(False, 255, 7, 17, 8, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # src_port is 3 bits
            SDPPacket(False, 255, 7, 17, -1, 0, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # src_cpu is 5 bits but should range 0..17
            SDPPacket(False, 255, 7, 17, 7, 18, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # src_cpu is 5 bits but should range 0..17
            SDPPacket(False, 255, 7, 17, 7, -1, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_x is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, 256, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_x is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, -1, 0, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_y is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, 255, 256, 0, 0, b'')

        with pytest.raises(ValueError):
            # dest_y is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, 255, -1, 0, 0, b'')

        with pytest.raises(ValueError):
            # src_x is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, 255, 255, 256, 0, b'')

        with pytest.raises(ValueError):
            # src_x is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, 255, 255, -1, 0, b'')

        with pytest.raises(ValueError):
            # src_y is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, 255, 255, 255, 256, b'')

        with pytest.raises(ValueError):
            # src_y is 8 bits
            SDPPacket(False, 255, 7, 17, 7, 17, 255, 255, 255, -1, b'')


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
        packet = b'\x87\xf0\xef\xee\x5a\xa5\xf0\x0f\xAD\xDE\xEF\xBE'
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
        packet = b'\x87\xf0\xef\xee\x5a\xa5\xf0\x0f\xAD\xDE\xEF\xBE' + \
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
        packet = b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
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
        packet = b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE'
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
        packet = b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
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
        packet = b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
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
        packet = b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
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
        packet = b'\x87\xf0\xef\xee\xa5\x5a\x0f\xf0\xAD\xDE\xEF\xBE' + \
                 b'\xB7\xB7\xA5\xA5\xFE\xCA\xFE\xCA'
        scp_packet = SCPPacket.from_bytestring(packet)

        assert scp_packet.arg1 == 0xA5A5B7B7
        assert scp_packet.arg2 == 0xCAFECAFE
        assert scp_packet.arg3 is None
        assert scp_packet.data == b''

        # Check that the bytestring this packet creates is the same as the one
        # we specified before.
        assert scp_packet.bytestring == packet

    def test_values(self):
        """Check that SCP packets respect data values."""
        with pytest.raises(ValueError):  # cmd_rc is 16 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      1 << 16, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):  # cmd_rc is 16 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      -1, 0, 0, 0, 0, b'')

        with pytest.raises(ValueError):  # seq is 16 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, 1 << 16, 0, 0, 0, b'')

        with pytest.raises(ValueError):  # seq is 16 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, -1, 0, 0, 0, b'')

        with pytest.raises(ValueError):  # arg1 is 32 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, 0xFFFF, 1 << 32, 0, 0, b'')

        with pytest.raises(ValueError):  # arg1 is 32 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, 0xFFFF, -1, 0, 0, b'')

        with pytest.raises(ValueError):  # arg2 is 32 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, 0xFFFF, 0xFFFFFFFF, 1 << 32, 0, b'')

        with pytest.raises(ValueError):  # arg2 is 32 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, 0xFFFF, 0xFFFFFFFF, -1, 0, b'')

        with pytest.raises(ValueError):  # arg3 is 32 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 1 << 32, b'')

        with pytest.raises(ValueError):  # arg3 is 32 bits
            SCPPacket(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                      0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, -1, b'')
