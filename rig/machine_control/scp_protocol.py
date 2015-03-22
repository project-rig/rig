"""A non-blocking implementation of the SCP protocol.

This class contains a Trollius (i.e. Python 2 backport of asyncio) protocol
which handles the sending and receiving of SCP packets.

.. Warning::
    All documentation refers to :py:mod:`asyncio` even though this
    implementation uses Trollius for Python 2 compatibility. This is because
    the Trollius API is identical to that of :py:mod:`asyncio` and is the
    recommended source of documentation.
"""

from six import itervalues

from collections import deque, namedtuple

from .packets import SCPPacket

import trollius


class SCPProtocol(trollius.DatagramProtocol):
    """A non-blocking implementation of SCP as a Trollius protocol.

    This protocol provides the ability to send many SCP packets simultaneously
    and to handle detecting time-outs and retransmission.

    Attributes
    ----------
    max_outstanding : int
        The maximum number of SCP commands which may remain outstanding
    timeout : float
        Number of seconds after which an SCP response is considered lost and
        retransmission is attempted.
    n_tries : int
        The maximum number of transmission attempts to make before timing out a
        packet.
    """

    _error_codes = {}
    """
    A mapping from CMD_RC values to appropriate exceptions. This dictionary is
    populated by use of the :py:meth:`.register_error` decorator.
    """

    def __init__(self, loop, max_outstanding=1, timeout=0.5, n_tries=5):
        """Create an SCPProtocol.

        Parameters
        ----------
        loop : :py:class:`asyncio.BaseEventLoop`
            The event loop in which this protocol will be running.
        max_outstanding : int
        timeout : float
        n_tries : int
        """
        self.loop = loop

        self.max_outstanding = max_outstanding
        self.timeout = timeout
        self.n_tries = n_tries

        # A queue of QueuedSCPRequest objects representing packets which have
        # not yet been sent.
        self.queue = deque()

        # A dictionary mapping SCP sequence numbers to OutstandingSCPRequest
        # objects representing packets which have been sent and are awaiting a
        # response.
        self.outstanding = {}

        # The DatagramTransport which backs this protocol or None if no
        # connection has been made.
        self.transport = None

        # If set, this exception will be immediately returned to all SCP
        # requests.
        self.died = None

        # The next 16-bit sequence number to apply to an SCP packet
        self._next_seq_num = 0

    @classmethod
    def register_error(cls, cmd_rc):
        """Decorator which registers an Exception class as belonging to a
        certain CMD_RC value.

        Whenever a response is received with the associated CMD_RC value, this
        exception will be sent to the command's sender.
        """
        def err_(err):
            cls._error_codes[cmd_rc] = err
            return err
        return err_

    def _get_seq_num(self):
        """Get a new SCP sequence number.

        .. warning::
            This command does not attempt to avoid re-using sequence numbers
            which are still in use since the sequence number count wrapped
            around. Since the sequence number is 16 bits, it is unlikely that
            once it wraps around any packets are still being retransmitted.
        """
        seq_num = self._next_seq_num
        self._next_seq_num = (self._next_seq_num + 1) & 0xFFFF
        return seq_num

    def send_scp(self, x, y, p, cmd, arg1=0, arg2=0, arg3=0,
                 data=b'', expected_args=3, additional_timeout=0.0):
        """Transmits a packet to the SpiNNaker machine and return a response
        via a Future.

        This function can be used in coroutines like so::

            scp_response =

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
        additional_timeout : float
            Additional timeout in seconds to wait for a reply on top of the
            default specified upon instantiation. Useful for commands like
            the BMP `power` command which take some time to complete.

        Returns
        -------
        :py:class:`asyncio.Future`
            Returns a future with a result of
            :py:class:`~rig.machine_control.packets.SCPPacket`: the packet that
            was received in acknowledgement of the transmitted packet.
        """
        future = trollius.Future(loop=self.loop)

        if self.died is not None:
            # Fail immediately if the connection died previously
            future.set_exception(self.died)
        else:
            # Construct the SCP packet
            seq_num = self._get_seq_num()
            data = b'\x00\x00' + SCPPacket(
                reply_expected=True, tag=0xff, dest_port=0, dest_cpu=p,
                src_port=7, src_cpu=31, dest_x=x, dest_y=y, src_x=0, src_y=0,
                cmd_rc=cmd, seq=seq_num,
                arg1=arg1, arg2=arg2, arg3=arg3, data=data
            ).bytestring

            # Place it in the queue
            self.queue.append(QueuedSCPRequest(
                future=future,
                seq_num=seq_num,
                expected_args=expected_args,
                additional_timeout=additional_timeout,
                data=data))

        # Trigger queue processing to cause the packet to get sent immediately
        # if possible
        self._process_queue()

        return future

    def _process_queue(self):
        """If possible, send some queued SCP packets."""
        # In practice the protocol object won't be available to the user to
        # prod until it has received its transport. However, defensive
        # programming...
        if self.transport is not None:  # pragma: no branch
            while len(self.outstanding) < self.max_outstanding and self.queue:
                queued_request = self.queue.popleft()
                # No point in sending cancelled packets
                if not queued_request.future.cancelled():
                    self._send_packet(queued_request)

    def _send_packet(self, queued_request, n_tries=1):
        """Make an attempt at sending an SDP packet.

        Parameters
        ----------
        queued_request : :py:class:`.QueuedSCPRequest`
            The packet to send.
        n_tries : int
            The number of attempts made to transmit the packet.
        """
        # XXX: Sequence number collisions should not occur in practice so this
        # assertion simply aims to make lots of noise if one does (rather than
        # handle it gracefully).
        assert queued_request.seq_num not in self.outstanding

        # Send the packet to machine
        self.transport.sendto(queued_request.data)

        # Setup a callback for the response timeout
        timer_handle = self.loop.call_later(
            self.timeout + queued_request.additional_timeout,
            self.on_timeout, queued_request.seq_num)

        # Record the outstanding packet
        self.outstanding[queued_request.seq_num] = OutstandingSCPRequest(
            queued_request=queued_request,
            timer_handle=timer_handle,
            n_tries=n_tries,
        )

    def on_timeout(self, seq_num):
        """Callback when an SCP packet response times out.

        Retransmit or drop the packet.
        """
        out_req = self.outstanding.pop(seq_num)
        new_n_tries = out_req.n_tries + 1

        if out_req.queued_request.future.cancelled():
            # Task cancelled, no point in re-transmitting. Handle some new
            # packets instead
            self._process_queue()
        elif new_n_tries > self.n_tries:
            # The packet has been retransmitted too many times, drop it
            out_req.queued_request.future.set_exception(TimeoutError(
                "Exceeded {} attempts trying to transmit packet.".format(
                    self.n_tries)))

            # Since a previously outstanding packet has now been serviced, a
            # new packet from the queue can potentially be processed.
            self._process_queue()
        else:
            # Retransmit
            self._send_packet(out_req.queued_request, new_n_tries)

    def datagram_received(self, data, addr):
        """Callback on a datagram arriving from the transport.

        Process the incoming SCP response.
        """
        # XXX: Silently ignores packets whose sequence number is not
        # recognised.
        seq_num = SCPPacket.from_bytestring(data[2:]).seq
        if seq_num in self.outstanding:
            out_req = self.outstanding.pop(seq_num)

            # Cancel the timeout
            out_req.timer_handle.cancel()

            # Fully-unpack the packet
            packet = SCPPacket.from_bytestring(
                data[2:], n_args=out_req.queued_request.expected_args)

            # Handle the response
            if out_req.queued_request.future.cancelled():
                # If the future was cancelled, there's no need to do anything
                # with the response: simply ignore it.
                pass
            if packet.cmd_rc not in self._error_codes:
                # The response is good, send it to the original requester
                if not out_req.queued_request.future.cancelled():
                    out_req.queued_request.future.set_result(packet)
            else:
                # The CMD_RC indicates that the command failed. Raise an
                # appropriate exception detailing the original packet sent.
                orig_packet = SCPPacket.from_bytestring(
                    out_req.queued_request.data[2:])
                if not out_req.queued_request.future.cancelled():
                    out_req.queued_request.future.set_exception(
                        self._error_codes[packet.cmd_rc](orig_packet))

            # Since an outstanding packet has now been serviced, a new packet
            # from the queue can potentially be processed.
            self._process_queue()

    def connection_made(self, transport):
        """Callback on transport becoming connected."""
        self.transport = transport
        self._process_queue()

    def error_received(self, exc):
        """Callback on error from transport.

        If any error is received, shut down the connection.
        """
        self.died = exc
        self.close()

    def connection_lost(self, exc):
        """Callback on connection closing from transport.

        Once the connection has been closed, report the closure to any
        outstanding/queued commands.
        """
        # Set an exception to send to all requests
        if self.died is None:
            if exc is not None:
                self.died = exc
            else:
                self.died = SCPConnectionClosed()

        # Send the exception to all outstanding and queued requests
        for req in itervalues(self.outstanding):
            if not req.queued_request.future.cancelled():
                req.queued_request.future.set_exception(self.died)
            req.timer_handle.cancel()
        for req in self.queue:
            if not req.future.cancelled():
                req.future.set_exception(self.died)

    def close(self):
        """Close the connection."""
        # In practice the protocol object won't be available to the user to
        # prod until it has received its transport. However, defensive
        # programming...
        if self.transport is not None:  # pragma: no branch
            self.transport.close()


class QueuedSCPRequest(namedtuple("QueuedSCPRequest",
                                  "future, seq_num, expected_args, "
                                  "additional_timeout, data")):
    """An SCP packet waiting to be sent.

    Parameters
    ----------
    future : :py:class:`asyncio.Future`
        A future which will be fulfilled by the response/timing out of the
        packet.
    seq_num : int
        Sequence number of the packet.
    expected_args : int
        The number of arguments (0-3) that are expected in the returned packet.
    additional_timeout : float
        Additional number of seconds allowed on top of regular timeout for the
        specified command before it times out.
    data : :py:class:`bytearray`
        The raw data which encodes the packet.
    """


class OutstandingSCPRequest(namedtuple("OutstandingSCPRequest",
                                       "queued_request, timer_handle, "
                                       "n_tries")):
    """An SCP packet waiting to be sent.

    Parameters
    ----------
    queued_request : :py:class:`.QueuedSCPRequest`
        The SCP request which is being dealt with.
    timer_handle : :py:class:`asyncio.Handle`
        The raw handle for the timer used to trigger retransmission/dropping of
        packets.
    n_tries : int
        The number of attempts made to send this packet.
    """


class SCPError(IOError):
    """Base Error for SCP-related errors."""
    pass


class TimeoutError(SCPError):
    """Raised when an SCP is not acknowledged within the given period of
    time and number of retries.
    """
    pass


class SCPConnectionClosed(SCPError):
    """Raised when an SCP command is sent via a connection which has been
    explicitly closed.
    """


class SCPResponseError(SCPError):
    """Base Error for SCP return codes."""
    def __init__(self, orig_packet):
        super(SCPResponseError, self).__init__(
            "Error in response to packet with arguments: "
            "cmd_rc={}, arg1={}, arg2={}, arg3={}; "
            "sent to core ({},{},{}).".format(
                orig_packet.cmd_rc,
                orig_packet.arg1,
                orig_packet.arg2,
                orig_packet.arg3,
                orig_packet.dest_x, orig_packet.dest_y,
                orig_packet.dest_cpu)
        )


@SCPProtocol.register_error(0x81)
class BadPacketLengthError(SCPResponseError):
    """Raised when an SCP packet is an incorrect length."""
    pass


@SCPProtocol.register_error(0x83)
class InvalidCommandError(SCPResponseError):
    """Raised when an SCP packet contains an invalid command code."""
    pass


@SCPProtocol.register_error(0x84)
class InvalidArgsError(SCPResponseError):
    """Raised when an SCP packet has an invalid argument."""
    pass


@SCPProtocol.register_error(0x87)
class NoRouteError(SCPResponseError):
    """Raised when there is no route to the requested core."""
