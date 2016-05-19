"""Internal-use functions shared between the
:py:class:`~rig.machine_control.MachineController` and
:py:class:`~rig.machine_control.BMPController` objects.
"""

import re


VERSION_NUMBER_REGEX = re.compile(r"^(\d+)[.](\d+)[.](\d+)(\D.*)?$")
"""A regular expression which splits up the key parts of a SemVer-like version
number. Captures the following groups:

1. The major version.
2. The minor version.
3. The patch level.
4. The pre-release version and any other build metadata.
"""


def unpack_sver_response_version(packet):
    """For internal use. Unpack the version-related parts of an sver (aka
    CMD_VERSION) response.

    Parameters
    ----------
    packet : :py:class:`~rig.machine_control.packets.SCPPacket`
        The packet recieved in response to the version command.

    Returns
    -------
    software_name : string
        The name of the software running on the remote machine.
    (major, minor, patch) : (int, int, int)
        The numerical part of the semantic version number.
    labels : string
        Any labels in the version number (e.g. '-dev'). May be an empty string.
    """
    software_name = packet.data.decode("utf-8")

    legacy_version_field = packet.arg2 >> 16

    if legacy_version_field != 0xFFFF:
        # Legacy version encoding: just encoded in decimal fixed-point in the
        # integer.
        major = legacy_version_field // 100
        minor = legacy_version_field % 100
        patch = 0
        labels = ""
    else:
        # Semantic Version encoding: packed after the null-terminator of the
        # software name in the version string.
        software_name, _, version_number = software_name.partition("\0")

        match = VERSION_NUMBER_REGEX.match(version_number.rstrip("\0"))
        assert match, "Malformed version number: {}".format(version_number)

        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        labels = match.group(4) or ""

    return (software_name.rstrip("\0"), (major, minor, patch), labels)
