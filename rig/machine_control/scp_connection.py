"""A stop-and-wait blocking implementation of the SCP protocol.
"""
import socket
from . import packets


class SCPConnection(object):
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

    def send_scp(self, x, y, p, cmd, arg1=0, arg2=0, arg3=0, data=b'',
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


class SCPError(IOError):
    """Base Error for SCP return codes."""
    pass


class TimeoutError(SCPError):
    """Raised when an SCP is not acknowledged within the given period of time.
    """
    pass


@SCPConnection._register_error(0x81)
class BadPacketLengthError(SCPError):
    """Raised when an SCP packet is an incorrect length."""
    pass


@SCPConnection._register_error(0x83)
class InvalidCommandError(SCPError):
    """Raised when an SCP packet contains an invalid command code."""
    pass


@SCPConnection._register_error(0x84)
class InvalidArgsError(SCPError):
    """Raised when an SCP packet has an invalid argument."""
    pass


@SCPConnection._register_error(0x87)
class NoRouteError(SCPError):
    """Raised when there is no route to the requested core."""
