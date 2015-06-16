"""Listen for a 'ping' broadcast message from an unbooted SpiNNaker board."""

from rig.machine_control.consts import BOOT_PORT

import socket


def listen(timeout=6.0, port=BOOT_PORT):
    """Listen for a 'ping' broadcast message from an unbooted SpiNNaker board.

    Unbooted SpiNNaker boards send out a UDP broadcast message every 4-ish
    seconds on port 54321. This function listens for such messages and reports
    the IP address that it came from.

    Parameters
    ----------
    timeout : float
        Number of seconds to wait for a message to arrive.
    port : int
        The port number to listen on.

    Returns
    -------
    str or None
        The IP address of the SpiNNaker board from which a ping was received or
        None if no ping was observed.
    """

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Don't take control of this socket in the system (i.e. allow other
    # processes to bind to it) since we're listening for broadcasts.
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Listen for the broadcasts
    s.bind(('0.0.0.0', port))
    s.settimeout(timeout)
    try:
        message, (ipaddr, port) = s.recvfrom(512)
        return ipaddr
    except socket.timeout:
        return None
