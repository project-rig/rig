from six import iteritems

import collections

from .scp_connection import SCPConnection

from . import consts

from .consts import SCPCommands, LEDAction

from rig.utils.contexts import ContextMixin, Required


class BMPController(ContextMixin):
    """Control the BMPs (Board Management Processors) onboard SpiNN-4 and
    SpiNN-5 boards in a SpiNNaker machine.

    BMPs (and thus boards) are addressed as follows::

                  2             1                0
        Cabinet --+-------------+----------------+
                  |             |                |
        +-------------+  +-------------+  +-------------+    Frame
        |             |  |             |  |             |      |
        | +---------+ |  | +---------+ |  | +---------+ |      |
        | | : : : : | |  | | : : : : | |  | | : : : : |--------+ 0
        | | : : : : | |  | | : : : : | |  | | : : : : | |      |
        | +---------+ |  | +---------+ |  | +---------+ |      |
        | | : : : : | |  | | : : : : | |  | | : : : : |--------+ 1
        | | : : : : | |  | | : : : : | |  | | : : : : | |      |
        | +---------+ |  | +---------+ |  | +---------+ |      |
        | | : : : : | |  | | : : : : | |  | | : : : : |--------+ 2
        | | : : : : | |  | | : : : : | |  | | : : : : | |      |
        | +---------+ |  | +---------+ |  | +---------+ |      |
        | | : : : : | |  | | : : : : | |  | | : : : : |--------+ 3
        | | : : : : | |  | | : : : : | |  | | : : : : | |
        | +---------+ |  | +|-|-|-|-|+ |  | +---------+ |
        |             |  |  | | | | |  |  |             |
        +-------------+  +--|-|-|-|-|--+  +-------------+
                            | | | | |
                 Board -----+-+-+-+-+
                            4 3 2 1 0

    Coordinates are conventionally written as 3-tuples of integers (cabinet,
    frame, board). This gives the upper-right-most board's coordinate (0, 0,
    0).

    Communication with BMPs is facilitated either directly via Ethernet or
    indirectly via the Ethernet connection of another BMP and the CAN bus in
    the backplane of each frame.

    This class aims not to be a complete BMP communication solution (users are
    referred instead to the general-purpose `bmpc` utility), but rather to
    cover common uses of the BMP in normal application usage.
    """

    def __init__(self, hosts, n_tries=5, timeout=0.5,
                 initial_context={"cabinet": 0, "frame": 0, "board": 0}):
        """Create a new controller for BMPs in a SpiNNaker machine.

        Parameters
        ----------
        hosts : string or {coord: string, ...}
            Hostname or IP address of the BMP to connect to or alternatively,
            multiple addresses can be given in a dictionary to allow control of
            many boards. `coord` may be given as ether (cabinet, frame) or
            (cabinet, frame, board) tuples. In the former case, the address
            will be used to communicate with all boards in the specified frame
            except those listed explicitly. If only a single hostname is
            supplied it is assumed to be for all boards in cabinet 0, frame 0.
        n_tries : int
            Number of SDP packet retransmission attempts.
        timeout : float
            SDP response timeout.
        initial_context : `{argument: value}`
            Dictionary of default arguments to pass to methods in this class.
            This defaults to selecting the coordinate (0, 0, 0) which is
            convenient in single-board systems.
        """
        # Initialise the context stack
        ContextMixin.__init__(self, initial_context)

        # Record paramters
        self.n_tries = n_tries
        self.timeout = timeout
        self._scp_data_length = None

        # Create connections
        if isinstance(hosts, str):
            hosts = {(0, 0): hosts}
        self.connections = {
            coord: SCPConnection(host, n_tries, timeout)
            for coord, host in iteritems(hosts)
        }

    @property
    def scp_data_length(self):
        if self._scp_data_length is None:
            # Select an arbitrary host to send an sver to (preferring
            # fully-specified hosts)
            coord = max(self.connections, key=len)
            if len(coord) == 2:
                coord = (coord[0], coord[1], 0)
            data = self.get_software_version(*coord)
            self._scp_data_length = data.buffer_size
        return self._scp_data_length

    def __call__(self, **context_args):
        """Create a new context for use with `with`."""
        return self.get_new_context(**context_args)

    @ContextMixin.use_named_contextual_arguments(
        cabinet=Required, frame=Required, board=Required)
    def send_scp(self, *args, **kwargs):
        """Transmit an SCP Packet to a specific board.

        See the arguments for
        :py:method:`~rig.machine_control.scp_connection.SCPConnection` for
        details.
        """
        # Retrieve contextual arguments from the keyword arguments.  The
        # context system ensures that these values are present.
        cabinet = kwargs.pop("cabinet")
        frame = kwargs.pop("frame")
        board = kwargs.pop("board")
        return self._send_scp(cabinet, frame, board, *args, **kwargs)

    def _send_scp(self, cabinet, frame, board, *args, **kwargs):
        """Determine the best connection to use to send an SCP packet and use
        it to transmit.

        See the arguments for
        :py:method:`~rig.machine_control.scp_connection.SCPConnection` for
        details.
        """
        # Find the connection which best matches the specified coordinates,
        # preferring direct connections to a board when available.
        connection = self.connections.get((cabinet, frame, board), None)
        if connection is None:
            connection = self.connections.get((cabinet, frame), None)
        assert connection is not None, \
            "No connection available to ({}, {}, {})".format(cabinet,
                                                             frame,
                                                             board)

        # Determine the size of packet we expect in return, this is usually the
        # size that we are informed we should expect by SCAMP/SARK or else is
        # the default.
        if self._scp_data_length is None:
            length = consts.SCP_SVER_RECEIVE_LENGTH_MAX
        else:
            length = self._scp_data_length

        return connection.send_scp(length, 0, 0, board, *args, **kwargs)

    @ContextMixin.use_contextual_arguments
    def get_software_version(self, cabinet=Required, frame=Required,
                             board=Required):
        """Get the software version for a given BMP.

        Returns
        -------
        :py:class:`BMPInfo`
            Information about the software running on a BMP.
        """
        sver = self._send_scp(cabinet, frame, board, SCPCommands.sver)

        # Format the result
        # arg1
        code_block = (sver.arg1 >> 24) & 0xff
        frame_id = (sver.arg1 >> 16) & 0xff
        can_id = (sver.arg1 >> 8) & 0xff
        board_id = sver.arg1 & 0xff

        # arg2
        version = (sver.arg2 >> 16) / 100.
        buffer_size = (sver.arg2 & 0xffff)

        return BMPInfo(code_block, frame_id, can_id, board_id, version,
                       buffer_size, sver.arg3, sver.data.decode("utf-8"))

    @ContextMixin.use_contextual_arguments
    def set_power(self, state, cabinet=Required, frame=Required,
                  board=Required, delay=0.0):
        """Control power to the SpiNNaker chips and FPGAs on a board.

        Returns
        -------
        state : bool
            True for power on, False for power off.
        board : int or iterable
            Specifies the board to control the power of. This may also be an
            iterable of multiple boards (in the same frame). The command will
            actually be sent to the first board in the iterable.
        delay : float
            Number of seconds delay between power state changes of different
            boards.
        """
        if isinstance(board, int):
            boards = [board]
        else:
            boards = list(board)
            board = boards[0]

        arg1 = int(delay * 1000) << 16 | (1 if state else 0)
        arg2 = sum(1 << b for b in boards)

        # Allow additional time for response when powering on (since FPGAs must
        # be loaded)
        self._send_scp(cabinet, frame, board, SCPCommands.power,
                       arg1=arg1, arg2=arg2,
                       timeout=consts.BMP_POWER_ON_TIMEOUT if state else None,
                       expected_args=0)

    @ContextMixin.use_contextual_arguments
    def set_led(self, led, action=None, cabinet=Required, frame=Required,
                board=Required):
        """Set or toggle the state of an LED.

        Parameters
        ----------
        led : int or iterable
            Number of the LED or an iterable of LEDs to set the state of (0-7)
        action : bool or None
            State to set the LED to. True for on, False for off, None to
            toggle (default).
        board : int or iterable
            Specifies the board to control the LEDs of. This may also be an
            iterable of multiple boards (in the same frame). The command will
            actually be sent to the first board in the iterable.
        """
        if isinstance(led, int):
            leds = [led]
        else:
            leds = led
        if isinstance(board, int):
            boards = [board]
        else:
            boards = list(board)
            board = boards[0]

        # LED setting actions
        arg1 = sum(LEDAction.from_bool(action) << (led * 2) for led in leds)

        # Bitmask of boards to control
        arg2 = sum(1 << b for b in boards)

        self._send_scp(cabinet, frame, board, SCPCommands.led, arg1=arg1,
                       arg2=arg2, expected_args=0)


class BMPInfo(collections.namedtuple(
    'BMPInfo', "code_block frame_id can_id board_id version buffer_size "
               "build_date version_string")):
    """Information returned about a BMP by sver.

    Parameters
    ----------
    code_block : int
        The BMP, on power-up, will execute the first valid block in its flash
        storage. This value which indicates which 64 KB block was selected.
    frame_id : int
        An identifier programmed into the EEPROM of the backplane which
        uniquely identifies the frame the board is in. Note: This ID is not
        necessarily the same as a board's frame-coordinate.
    can_id : int
        ID of the board in the backplane CAN bus.
    board_id : int
        The position of the board in a frame. (This should correspond exactly
        with a board's board-coordinate.
    version : float
        Software version number. (Major version is integral part, minor version
        is fractional part).
    buffer_size : int
        Maximum supported size (in bytes) of the data portion of an SCP packet.
    build_date : int
        The time at which the software was compiled as a unix timestamp. May be
        zero if not set.
    version_string : string
        Human readable, textual version information split in to two fields by a
        "/". In the first field is the kernel (e.g. BC&MP) and the second the
        hardware platform (e.g. Spin5-BMP).
    """
