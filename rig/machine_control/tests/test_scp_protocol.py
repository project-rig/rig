"""Tests of SCPProtocol.

These tests are largely run against a simple UDP echo server
(MockSpiNNakerProtocol) which bounces packets back after a delay/number of
attempts indicated in the incoming packet.
"""

import pytest

from collections import defaultdict

import time

from six import iteritems

import trollius
from trollius import From, Return

from rig.machine_control.packets import SCPPacket
from ..scp_protocol import SCPProtocol, \
    SCPError, TimeoutError, BadPacketLengthError, InvalidCommandError, \
    InvalidArgsError, NoRouteError, SCPConnectionClosed


@pytest.yield_fixture
def loop():
    """Build a new event loop with a safety timeout of 1 sec."""
    loop = trollius.new_event_loop()

    def timeout():  # pragma: no cover
        loop.stop()
        raise Exception("Test event loop killed after timeout.")
    handle = loop.call_later(1.0, timeout)

    yield loop

    handle.cancel()
    loop.close()


class MockSpiNNakerProtocol(trollius.DatagramProtocol):
    """A protocol which pretends to be a SpiNNaker system.

    Sent packets are echoed back with dest_x and dest_y being used to determine
    when the response is sent. dest_cpu gives the number of duplicate responses
    to send (to ensure unexpected sequence numbers are ignored).

    * dest_x contains the number of msec to sleep before sending a reply
    * dest_y is the number of attempts required before a response is sent (0
      means never reply)
    * dest_cpu Number of duplicate responses

    Attributes
    ----------
    received : [:py:class:`bytearray`, ...]
        Ordered list of packets which arrived.
    """
    def __init__(self, loop):
        self.loop = loop
        self.received = []
        self.transport = None

        # Count of packets received with a given sequence number
        self.n_tries = defaultdict(lambda: 0)

        # A list of handlers for *all* call_later calls (even ones which have
        # occurred)
        self.delayed_sends = list()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        """Bounce incoming packets as required."""
        # Log the packet
        self.received.append(data)

        packet = SCPPacket.from_bytestring(data[2:])

        print("MockSpiNNakerProtocol: Packet arrived: "
              "cmd={}, dest_x={}, dest_y={}, seq={}".format(packet.cmd_rc,
                                                            packet.dest_x,
                                                            packet.dest_y,
                                                            packet.seq))

        self.n_tries[packet.seq] += 1

        sleep = packet.dest_x / 1000.
        n_tries = packet.dest_y
        duplicates = packet.dest_cpu

        # If the required number of tries have been performed, echo back the
        # packet!
        if self.n_tries[packet.seq] == n_tries:
            print("MockSpiNNakerProtocol: Respond in {} sec.".format(sleep))
            self.delayed_sends.append(
                self.loop.call_later(sleep, self.send_back,
                                     data, addr, duplicates))
        else:
            print("MockSpiNNakerProtocol: Ignoring try {}/{}.".format(
                self.n_tries[packet.seq], n_tries))

    def send_back(self, data, addr, duplicates):
        """Callback for delayed packet sends."""
        print("MockSpiNNakerProtocol: Sending response.")
        for _ in range(1+duplicates):
            self.transport.sendto(data, addr)

    def connection_lost(self, exc):  # pragma: no cover
        print("MockSpiNNakerProtocol: Connection lost: {}".format(exc))
        self.close()

    def close(self):
        for handle in self.delayed_sends:
            handle.cancel()


@pytest.yield_fixture
def create_fake_machine(loop):
    """Attaches a fake SpiNNaker machine to a random UDP port number.

    Returns a coroutine function which will create a local server on some UDP
    port returning a (protocol, addr) pair. The protocol can be used to
    check what messages have been sent, the addr can be used to connect a
    SCPProtocol.
    """

    transport = []
    protocol = []

    @trollius.coroutine
    def create_fake_machine_server():
        t, p = yield From(loop.create_datagram_endpoint(  # pragma: no branch
            (lambda: MockSpiNNakerProtocol(loop)),
            ("127.0.0.1", 0)))
        transport.append(t)
        protocol.append(p)
        raise Return(p, t.get_extra_info("sockname"))

    yield create_fake_machine_server

    # Close ports and cancel outstanding responses in the fake machine
    for t in transport:
        t.close()
    for p in protocol:
        p.close()


@pytest.yield_fixture
def create_scp_protocol(loop):
    """Return a coroutine which returns an SCPProtocol connected to the
    supplied address.
    """
    transport = []
    protocol = []

    @trollius.coroutine
    def connect_scp_protocol(addr):
        t, p = yield From(loop.create_datagram_endpoint(  # pragma: no branch
            lambda: SCPProtocol(loop),
            remote_addr=addr))
        transport.append(t)
        protocol.append(p)
        raise Return(p)
    yield connect_scp_protocol

    # Close ports and cancel outstanding responses in the fake machine
    for t in transport:
        t.close()
    for p in protocol:
        p.close()


@pytest.fixture
def connected_protocols(loop, create_fake_machine, create_scp_protocol):
    """Fixture which provides a connected fake spinnaker machine and
    SCPProtocol.

    This fixture returns a MockSpiNNakerProtocol and a SCPProtocol as a pair
    (mock_spinnaker_protocol, scp_protocol) which are connected ready to use.
    """

    @trollius.coroutine
    def initialise_test_protocols():
        mock_spinnaker_protocol, addr = yield From(create_fake_machine())
        scp_protocol = yield From(create_scp_protocol(addr))
        raise Return(mock_spinnaker_protocol, scp_protocol)

    return loop.run_until_complete(initialise_test_protocols())


@pytest.fixture
def mock_spinnaker_protocol(connected_protocols):
    """Convenience wrapper around connected_protocols."""
    return connected_protocols[0]


@pytest.fixture
def scp_protocol(connected_protocols):
    """Convenience wrapper around connected_protocols."""
    return connected_protocols[1]


@pytest.mark.parametrize("expected_args, kwargs",
                         [(3, {"arg1": 1111, "arg2": 2222, "arg3": 3333}),
                          (2, {"arg1": 1111, "arg2": 2222, "arg3": None}),
                          (1, {"arg1": 1111, "arg2": None, "arg3": None}),
                          (0, {"arg1": None, "arg2": None, "arg3": None})])
def test_single_success(loop, mock_spinnaker_protocol, scp_protocol,
                        expected_args, kwargs):
    """Test the successful transmission/response of a single message."""
    response = loop.run_until_complete(scp_protocol.send_scp(
        x=0, y=1, p=0, cmd=3, data=b"Hello, world!",
        expected_args=expected_args, **kwargs))

    # Check request matches
    assert len(mock_spinnaker_protocol.received) == 1
    request = SCPPacket.from_bytestring(
        mock_spinnaker_protocol.received.pop()[2:],
        n_args=expected_args)
    assert request.dest_x == 0
    assert request.dest_y == 1
    assert request.dest_cpu == 0
    assert request.cmd_rc == 3
    assert request.data == b"Hello, world!"
    for arg, value in iteritems(kwargs):
        assert getattr(request, arg) == value

    # Check response matches
    assert response.dest_x == 0
    assert response.dest_y == 1
    assert response.dest_cpu == 0
    assert response.cmd_rc == 3
    assert response.data == b"Hello, world!"
    for arg, value in iteritems(kwargs):
        assert getattr(response, arg) == value


def test_retry(loop, mock_spinnaker_protocol, scp_protocol):
    """Test the successful transmission/response of a single message when
    retries are required.
    """
    scp_protocol.timeout = 0.05
    scp_protocol.n_tries = 3

    before = time.time()
    response = loop.run_until_complete(scp_protocol.send_scp(
        x=0, y=3, p=0, cmd=3, data=b"Hello, world!",
        arg1=None, arg2=None, arg3=None, expected_args=0))
    after = time.time()

    # Check the right number of attempts were made
    assert len(mock_spinnaker_protocol.received) == 3

    # Check that the timeout elapsed each time
    assert after - before >= (scp_protocol.n_tries - 1) * scp_protocol.timeout

    # Check requests arrived and that they match
    for data in mock_spinnaker_protocol.received:
        request = SCPPacket.from_bytestring(data[2:], n_args=0)
        assert request.dest_x == 0
        assert request.dest_y == 3
        assert request.dest_cpu == 0
        assert request.cmd_rc == 3
        assert request.data == b"Hello, world!"

    # Check response matches
    assert response.dest_x == 0
    assert response.dest_y == 3
    assert response.dest_cpu == 0
    assert response.cmd_rc == 3
    assert response.data == b"Hello, world!"


def test_timeout(loop, mock_spinnaker_protocol, scp_protocol):
    """Test timeouts occur correctly."""
    scp_protocol.timeout = 0.05
    scp_protocol.n_tries = 1

    # Ensure the packet times out
    before = time.time()
    with pytest.raises(TimeoutError):
        loop.run_until_complete(scp_protocol.send_scp(
            x=100, y=1, p=0, cmd=3, data=b"Hello, world!",
            arg1=None, arg2=None, arg3=None, expected_args=0))
    after = time.time()

    # Check that the timeout elapsed
    assert after - before >= scp_protocol.timeout

    # Check only one attempt was made
    assert len(mock_spinnaker_protocol.received) == 1

    # Check the request was correct
    data = mock_spinnaker_protocol.received.pop()
    request = SCPPacket.from_bytestring(data[2:], n_args=0)
    assert request.dest_x == 100
    assert request.dest_y == 1
    assert request.dest_cpu == 0
    assert request.cmd_rc == 3
    assert request.data == b"Hello, world!"


@pytest.mark.parametrize(
    "rc, error",
    [(0x81, BadPacketLengthError),
     (0x83, InvalidCommandError),
     (0x84, InvalidArgsError),
     (0x87, NoRouteError)])
def test_errors(loop, mock_spinnaker_protocol, scp_protocol, rc, error):
    """Test error responses cause the appropriate exceptions."""
    scp_protocol.timeout = 0.05
    scp_protocol.n_tries = 1

    # Ensure the error comes back as an exception
    with pytest.raises(error):
        loop.run_until_complete(scp_protocol.send_scp(
            x=0, y=1, p=0, cmd=rc, data=b"Hello, world!",
            arg1=None, arg2=None, arg3=None, expected_args=0))

    # Check only one attempt was made
    assert len(mock_spinnaker_protocol.received) == 1

    # Check the request was correct
    data = mock_spinnaker_protocol.received.pop()
    request = SCPPacket.from_bytestring(data[2:], n_args=0)
    assert request.dest_x == 0
    assert request.dest_y == 1
    assert request.dest_cpu == 0
    assert request.cmd_rc == rc
    assert request.data == b"Hello, world!"


def test_cancelled_before_sent(loop, mock_spinnaker_protocol, scp_protocol):
    """Test that packets cancelled before they get sent never get sent."""
    # This one will get through
    fut1 = scp_protocol.send_scp(x=1, y=1, p=0, cmd=3, data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    # This one will be cancelled (and because it will be held up by the first
    # packet, it should never get sent)
    fut2 = scp_protocol.send_scp(x=1, y=1, p=0, cmd=4, data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    # This one will get through
    fut3 = scp_protocol.send_scp(x=1, y=1, p=0, cmd=3, data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    fut2.cancel()
    loop.run_until_complete(trollius.gather(fut1, fut3, loop=loop,
                                            return_exceptions=True))

    # Check only the second request got sent
    assert len(mock_spinnaker_protocol.received) == 2
    for data in mock_spinnaker_protocol.received:
        request = SCPPacket.from_bytestring(data[2:], n_args=0)
        assert request.dest_x == 1
        assert request.dest_y == 1
        assert request.dest_cpu == 0
        assert request.cmd_rc == 3
        assert request.data == b"Hello, world!"


def test_cancelled_before_resend(loop, mock_spinnaker_protocol, scp_protocol):
    """Test that packets cancelled before they get re-transmitted."""
    scp_protocol.n_tries = 2
    scp_protocol.timeout = 0.01

    # This one will be cancelled just before its first retransmit
    fut1 = scp_protocol.send_scp(x=1, y=0, p=0, cmd=3, data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    loop.call_later(0.005, fut1.cancel)

    # This one will get through after the first has been dropped due to
    # cancellation
    fut2 = scp_protocol.send_scp(x=1, y=1, p=0, cmd=3, data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    loop.run_until_complete(fut2)

    # Check both things only got sent once
    assert len(mock_spinnaker_protocol.received) == 2
    for num, data in enumerate(mock_spinnaker_protocol.received):
        request = SCPPacket.from_bytestring(data[2:], n_args=0)
        assert request.dest_x == 1
        assert request.dest_y == num
        assert request.dest_cpu == 0
        assert request.cmd_rc == 3
        assert request.data == b"Hello, world!"


@pytest.mark.parametrize("is_error, rc_base", [(False, 0), (True, 0x83)])
def test_cancelled_before_response(loop, mock_spinnaker_protocol, scp_protocol,
                                   is_error, rc_base):
    """Test that packets cancelled before they return doesn't break anything"""
    # This one will get cancelled after it arrives at the server but before it
    # bounces back.
    fut1 = scp_protocol.send_scp(x=10, y=1, p=0, cmd=rc_base + 0,
                                 data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    loop.call_later(0.001, fut1.cancel)

    # This one will not get cancelled but will arrive afterwards
    fut2 = scp_protocol.send_scp(x=10, y=1, p=0, cmd=rc_base + 1,
                                 data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)

    if is_error:
        # Make sure the second error came back
        with pytest.raises(SCPError):
            loop.run_until_complete(fut2)
    else:
        # Make sure the second request came back
        response = loop.run_until_complete(fut2)
        assert response.dest_x == 10
        assert response.dest_y == 1
        assert response.dest_cpu == 0
        assert response.cmd_rc == 1
        assert response.data == b"Hello, world!"

    # Make sure the first request did get cancelled
    assert fut1.cancelled()

    # Make sure both requests arrived at the server
    assert len(mock_spinnaker_protocol.received) == 2
    for num, data in enumerate(mock_spinnaker_protocol.received):
        request = SCPPacket.from_bytestring(data[2:], n_args=0)
        assert request.dest_x == 10
        assert request.dest_y == 1
        assert request.dest_cpu == 0
        assert request.cmd_rc == rc_base + num
        assert request.data == b"Hello, world!"


def test_multiple_outstanding(loop, mock_spinnaker_protocol, scp_protocol):
    """Test that if multiple outstanding commands can be sent."""
    scp_protocol.max_outstanding = 3
    scp_protocol.n_tries = 2
    scp_protocol.timeout = 0.100

    # Generate a packet that will never come back and which will otherwise be
    # stuck being re-transmitted.
    stuck = scp_protocol.send_scp(x=0, y=0, p=0, cmd=0,
                                  data=b"Hello, world!",
                                  arg1=None, arg2=None, arg3=None,
                                  expected_args=0)

    # Generate 8 packets which turn around after 50ms each. These will be sent
    # in parallel and should be handled in two groups of two (since the third
    # slot is used up by the stuck packet).
    send = []
    for _ in range(8):
        send.append(scp_protocol.send_scp(x=50, y=1, p=0, cmd=0,
                                          data=b"Hello, world!",
                                          arg1=None, arg2=None, arg3=None,
                                          expected_args=0))

    # Wait for all the packets to be responded to or time out
    before = time.time()
    responses = loop.run_until_complete(trollius.gather(
        *([stuck] + send), loop=loop, return_exceptions=True))
    after = time.time()

    # Time elapsed should have been about the time required to send two packets
    # (since the timeout took 2*100ms and the four rounds of parallel sends
    # took 50ms each). This test allows a little margin for slow execution.
    assert 0.20 <= after - before < 0.30

    # The stuck packet should time out
    assert isinstance(responses[0], TimeoutError)

    # The other packets should all arrive intact
    for response in responses[1:]:
        assert response.dest_x == 50
        assert response.dest_y == 1
        assert response.dest_cpu == 0
        assert response.cmd_rc == 0
        assert response.data == b"Hello, world!"

    # The stuck packet should have been sent twice while the other packets
    # should have been sent once each
    num_stuck = 0
    num_sent = 0
    for num, data in enumerate(mock_spinnaker_protocol.received):
        request = SCPPacket.from_bytestring(data[2:], n_args=0)
        was_stuck = all((request.dest_x == 0,
                         request.dest_y == 0,
                         request.dest_cpu == 0,
                         request.cmd_rc == 0,
                         request.data == b"Hello, world!"))
        was_sent = all((request.dest_x == 50,
                        request.dest_y == 1,
                        request.dest_cpu == 0,
                        request.cmd_rc == 0,
                        request.data == b"Hello, world!"))
        assert was_stuck ^ was_sent
        if was_stuck:
            num_stuck += 1
        if was_sent:
            num_sent += 1
    assert num_stuck == 2
    assert num_sent == 8


def test_dead_connection(loop, mock_spinnaker_protocol, scp_protocol):
    """Test that requests fail sensibly when the connection dies."""
    scp_protocol.max_outstanding = 2

    # Send a command which will arrive but its reply will be blocked by the
    # connection being closed
    fut1 = scp_protocol.send_scp(x=0, y=0, p=0, cmd=3, data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    # And one which will be cancelled after it has been sent
    fut1c = scp_protocol.send_scp(x=0, y=0, p=0, cmd=3, data=b"Hello, world!",
                                  arg1=None, arg2=None, arg3=None,
                                  expected_args=0)
    loop.call_later(0.001, fut1c.cancel)

    # Kill the connection after the first packets have been sent and while
    # we're waiting for their response
    loop.call_later(0.002, scp_protocol.transport.close)

    # Queue up another packet which will get killed before it is even sent
    fut2 = scp_protocol.send_scp(x=0, y=0, p=0, cmd=3, data=b"Hello, world!",
                                 arg1=None, arg2=None, arg3=None,
                                 expected_args=0)
    # And one which will be queued but cancelled
    fut2c = scp_protocol.send_scp(x=0, y=0, p=0, cmd=3, data=b"Hello, world!",
                                  arg1=None, arg2=None, arg3=None,
                                  expected_args=0)
    loop.call_later(0.001, fut2c.cancel)

    # Run the system and check both non-cancelled requests failed
    responses = loop.run_until_complete(trollius.gather(
        fut1, fut2, loop=loop, return_exceptions=True))
    for response in responses:
        assert isinstance(response, SCPConnectionClosed)

    # The first two commands should have been sent, though! Make sure they
    # arrived.
    assert len(mock_spinnaker_protocol.received) == 2
    for num, data in enumerate(mock_spinnaker_protocol.received):
        request = SCPPacket.from_bytestring(data[2:], n_args=0)
        assert request.dest_x == 0
        assert request.dest_y == 0
        assert request.dest_cpu == 0
        assert request.cmd_rc == 3
        assert request.data == b"Hello, world!"

    # Make a new request which should be immediately rejected before being
    # dispatched.
    with pytest.raises(SCPConnectionClosed):
        loop.run_until_complete(scp_protocol.send_scp(x=0, y=0, p=0, cmd=3,
                                                      data=b"Hello, world!",
                                                      expected_args=0))


def test_unexpected_seq_number(loop, scp_protocol):
    """Test that when responses are sent multiple times, the duplicates are
    silently ignored."""
    futs = []
    # Send several packets which will receive duplicate replies
    for _ in range(4):
        futs.append(scp_protocol.send_scp(x=0, y=1, p=1, cmd=3,
                                          arg1=None, arg2=None, arg3=None,
                                          data=b"Hello, world!",
                                          expected_args=0))

    # Check all return correctly
    responses = loop.run_until_complete(trollius.gather(
        *futs, loop=loop, return_exceptions=True))
    for response in responses:
        assert response.dest_x == 0
        assert response.dest_y == 1
        assert response.dest_cpu == 1
        assert response.cmd_rc == 3
        assert response.data == b"Hello, world!"


def test_error_received(loop, mock_spinnaker_protocol, scp_protocol):
    """Falsely trigger the error_received callback and make sure the error
    propagates."""

    class FakeException(Exception):
        pass

    scp_protocol.error_received(FakeException())

    # Make sure future requests all get this exception in response.
    with pytest.raises(FakeException):
        loop.run_until_complete(scp_protocol.send_scp(
            x=0, y=1, p=0, cmd=0, data=b"Hello, world!",
            arg1=None, arg2=None, arg3=None, expected_args=0))


def test_connection_lost_error(loop, mock_spinnaker_protocol, scp_protocol):
    """Falsely trigger the connection_lost callback with an exception and make
    sure the error propagates."""

    class FakeException(Exception):
        pass

    scp_protocol.connection_lost(FakeException())

    # Make sure future requests all get this exception in response.
    with pytest.raises(FakeException):
        loop.run_until_complete(scp_protocol.send_scp(
            x=0, y=1, p=0, cmd=0, data=b"Hello, world!",
            arg1=None, arg2=None, arg3=None, expected_args=0))
