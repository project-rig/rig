import pytest
from mock import Mock

from rig.machine_control.packets import SCPPacket

from rig.machine_control.common import unpack_sver_response_version


@pytest.mark.parametrize("new_style", [True, False])
@pytest.mark.parametrize("labels", ["", "-dev"])
def test_unpack_sver_response_version(new_style, labels):
    packet = Mock(spec_set=SCPPacket)

    if new_style:
        packet.arg2 = 0xFFFF << 16
        packet.data = "My Software\0001.2.3{}\0".format(labels).encode("ASCII")
    else:
        packet.arg2 = 123 << 16
        packet.data = b"My Software\0"

    software_name, (major, minor, patch), actual_labels = \
        unpack_sver_response_version(packet)

    assert software_name == "My Software"

    if new_style:
        assert major == 1
        assert minor == 2
        assert patch == 3
        assert actual_labels == labels
    else:
        assert major == 1
        assert minor == 23
        assert patch == 0
        assert actual_labels == ""
