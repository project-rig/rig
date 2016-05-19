from six import iteritems

import time
import struct
import collections

from rig.machine_control.scp_connection import SCPConnection

from rig.machine_control import consts

from rig.machine_control.consts import SCPCommands, LEDAction, BMPInfoType, \
    BMP_V_SCALE_2_5, BMP_V_SCALE_3_3, BMP_V_SCALE_12, BMP_TEMP_SCALE, \
    BMP_MISSING_TEMP, BMP_MISSING_FAN
from rig.machine_control.common import unpack_sver_response_version

from rig.utils.contexts import ContextMixin, Required


class BMPController(ContextMixin):
    """Control the BMPs (Board Management Processors) onboard SpiNN-5 boards in
    a SpiNNaker machine.

    A :ref:`tutorial <BMPController-tutorial>` is available which introduces
    the basic features of this class.

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

    def __init__(self, hosts, scp_port=consts.SCP_PORT, n_tries=5, timeout=0.5,
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
        scp_port : int
            Port number to use for all SCP connections
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
        self.scp_port = scp_port
        self.n_tries = n_tries
        self.timeout = timeout
        self._scp_data_length = None

        # Create connections
        if isinstance(hosts, str):
            hosts = {(0, 0): hosts}
        self.connections = {
            coord: SCPConnection(host, scp_port, n_tries, timeout)
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

    @ContextMixin.use_contextual_arguments(
        cabinet=Required, frame=Required, board=Required)
    def send_scp(self, *args, **kwargs):
        """Transmit an SCP Packet to a specific board.

        Automatically determines the appropriate connection to use.

        See the arguments for
        :py:meth:`~rig.machine_control.scp_connection.SCPConnection` for
        details.

        Parameters
        ----------
        cabinet : int
        frame : int
        board : int
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
        :py:meth:`~rig.machine_control.scp_connection.SCPConnection` for
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

    @ContextMixin.use_contextual_arguments()
    def get_software_version(self, cabinet, frame, board):
        """Get the software version for a given BMP.

        Returns
        -------
        :py:class:`.BMPInfo`
            Information about the software running on a BMP.
        """
        sver = self._send_scp(cabinet, frame, board, SCPCommands.sver)

        # Format the result
        # arg1
        code_block = (sver.arg1 >> 24) & 0xff
        frame_id = (sver.arg1 >> 16) & 0xff
        can_id = (sver.arg1 >> 8) & 0xff
        board_id = sver.arg1 & 0xff

        # arg2 (version field unpacked separately)
        buffer_size = (sver.arg2 & 0xffff)

        software_name, version, version_labels = \
            unpack_sver_response_version(sver)

        return BMPInfo(code_block, frame_id, can_id, board_id, version,
                       buffer_size, sver.arg3, software_name, version_labels)

    @ContextMixin.use_contextual_arguments()
    def set_power(self, state, cabinet, frame, board,
                  delay=0.0, post_power_on_delay=5.0):
        """Control power to the SpiNNaker chips and FPGAs on a board.

        Returns
        -------
        state : bool
            True for power on, False for power off.
        board : int or iterable
            Specifies the board to control the power of. This may also be an
            iterable of multiple boards (in the same frame). The command will
            actually be sent board 0, regardless of the set of boards
            specified.
        delay : float
            Number of seconds delay between power state changes of different
            boards.
        post_power_on_delay : float
            Number of seconds for this command to block once the power on
            command has been carried out. A short delay (default) is useful at
            this point since power-supplies and SpiNNaker chips may still be
            coming on line immediately after the power-on command is sent.

            .. warning::
                If the set of boards to be powered-on does not include board 0,
                this timeout should be extended by 2-3 seconds. This is due to
                the fact that BMPs immediately acknowledge power-on commands to
                boards other than board 0 but wait for the FPGAs to be loaded
                before responding when board 0 is powered on.
        """
        if isinstance(board, int):
            boards = [board]
        else:
            boards = list(board)

        arg1 = int(delay * 1000) << 16 | (1 if state else 0)
        arg2 = sum(1 << b for b in boards)

        # Allow additional time for response when powering on (since FPGAs must
        # be loaded). Also, always send the command to board 0. This is
        # required by the BMPs which do not correctly handle the power-on
        # command being sent to anything but board 0. Though this is a bug in
        # the BMP firmware, it is considered sufficiently easy to work-around
        # that no fix is planned.
        self._send_scp(cabinet, frame, 0, SCPCommands.power,
                       arg1=arg1, arg2=arg2,
                       timeout=consts.BMP_POWER_ON_TIMEOUT if state else 0.0,
                       expected_args=0)
        if state:
            time.sleep(post_power_on_delay)

    @ContextMixin.use_contextual_arguments()
    def set_led(self, led, action=None,
                cabinet=Required, frame=Required, board=Required):
        """Set or toggle the state of an LED.

        .. note::
            At the time of writing, LED 7 is only set by the BMP on start-up to
            indicate that the watchdog timer reset the board. After this point,
            the LED is available for use by applications.

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

    @ContextMixin.use_contextual_arguments()
    def read_fpga_reg(self, fpga_num, addr, cabinet, frame, board):
        """Read the value of an FPGA (SPI) register.

        See the SpI/O project's spinnaker_fpga design's `README`_ for a listing
        of FPGA registers. The SpI/O project can be found on GitHub at:
        https://github.com/SpiNNakerManchester/spio/

        .. _README: https://github.com/SpiNNakerManchester/spio/\
                    blob/master/designs/spinnaker_fpgas/README.md#spi-interface

        Parameters
        ----------
        fpga_num : int
            FPGA number (0, 1 or 2) to communicate with.
        addr : int
            Register address to read to (will be rounded down to the nearest
            32-bit word boundary).

        Returns
        -------
        int
            The 32-bit value at that address.
        """
        arg1 = addr & (~0x3)
        arg2 = 4  # Read a 32-bit value
        arg3 = fpga_num
        response = self._send_scp(cabinet, frame, board, SCPCommands.link_read,
                                  arg1=arg1, arg2=arg2, arg3=arg3,
                                  expected_args=0)
        return struct.unpack("<I", response.data)[0]

    @ContextMixin.use_contextual_arguments()
    def write_fpga_reg(self, fpga_num, addr, value, cabinet, frame, board):
        """Write the value of an FPGA (SPI) register.

        See the SpI/O project's spinnaker_fpga design's `README`_ for a listing
        of FPGA registers. The SpI/O project can be found on GitHub at:
        https://github.com/SpiNNakerManchester/spio/

        .. _README: https://github.com/SpiNNakerManchester/spio/\
                    blob/master/designs/spinnaker_fpgas/README.md#spi-interface

        Parameters
        ----------
        fpga_num : int
            FPGA number (0, 1 or 2) to communicate with.
        addr : int
            Register address to read or write to (will be rounded down to the
            nearest 32-bit word boundary).
        value : int
            A 32-bit int value to write to the register
        """
        arg1 = addr & (~0x3)
        arg2 = 4  # Write a 32-bit value
        arg3 = fpga_num
        self._send_scp(cabinet, frame, board, SCPCommands.link_write,
                       arg1=arg1, arg2=arg2, arg3=arg3,
                       data=struct.pack("<I", value), expected_args=0)

    @ContextMixin.use_contextual_arguments()
    def read_adc(self, cabinet, frame, board):
        """Read ADC data from the BMP including voltages and temperature.

        Returns
        -------
        :py:class:`.ADCInfo`
        """
        response = self._send_scp(cabinet, frame, board, SCPCommands.bmp_info,
                                  arg1=BMPInfoType.adc, expected_args=0)
        data = struct.unpack("<"   # Little-endian
                             "8H"  # uint16_t adc[8]
                             "4h"  # int16_t t_int[4]
                             "4h"  # int16_t t_ext[4]
                             "4h"  # int16_t fan[4]
                             "I"   # uint32_t warning
                             "I",  # uint32_t shutdown
                             response.data)

        return ADCInfo(
            voltage_1_2c=data[1] * BMP_V_SCALE_2_5,
            voltage_1_2b=data[2] * BMP_V_SCALE_2_5,
            voltage_1_2a=data[3] * BMP_V_SCALE_2_5,
            voltage_1_8=data[4] * BMP_V_SCALE_2_5,
            voltage_3_3=data[6] * BMP_V_SCALE_3_3,
            voltage_supply=data[7] * BMP_V_SCALE_12,
            temp_top=float(data[8]) * BMP_TEMP_SCALE,
            temp_btm=float(data[9]) * BMP_TEMP_SCALE,
            temp_ext_0=((float(data[12]) * BMP_TEMP_SCALE)
                        if data[12] != BMP_MISSING_TEMP else None),
            temp_ext_1=((float(data[13]) * BMP_TEMP_SCALE)
                        if data[13] != BMP_MISSING_TEMP else None),
            fan_0=float(data[16]) if data[16] != BMP_MISSING_FAN else None,
            fan_1=float(data[17]) if data[17] != BMP_MISSING_FAN else None,
        )


class BMPInfo(collections.namedtuple(
    'BMPInfo', "code_block frame_id can_id board_id version buffer_size "
               "build_date version_string version_labels")):
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
    version : (major, minor, patch)
        Software version number. See also: ``version_labels``.
    buffer_size : int
        Maximum supported size (in bytes) of the data portion of an SCP packet.
    build_date : int
        The time at which the software was compiled as a unix timestamp. May be
        zero if not set.
    version_string : string
        Human readable, textual version information split in to two fields by a
        "/". In the first field is the kernel (e.g. BC&MP) and the second the
        hardware platform (e.g. Spin5-BMP).
    version_labels : string
        Any additional labels or build information associated with the software
        version. (See also: ``version`` and the `Semantic Versioning
        <http://semver.org/>`_ specification).
    """


class ADCInfo(collections.namedtuple(
    'ADCInfo', "voltage_1_2c voltage_1_2b voltage_1_2a voltage_1_8 "
               "voltage_3_3 voltage_supply "
               "temp_top temp_btm temp_ext_0 temp_ext_1 fan_0 fan_1")):
    """ADC data returned by a BMP including voltages and temperature.

    Parameters
    ----------
    voltage_1_2a : float
        Measured voltage on the 1.2 V rail A.
    voltage_1_2b : float
        Measured voltage on the 1.2 V rail B.
    voltage_1_2c : float
        Measured voltage on the 1.2 V rail C.
    voltage_1_8 : float
        Measured voltage on the 1.8 V rail.
    voltage_3_3 : float
        Measured voltage on the 3.3 V rail.
    voltage_supply : float
        Measured voltage of the (12 V) power supply input.
    temp_top : float
        Temperature near the top of the board (degrees Celsius)
    temp_btm : float
        Temperature near the bottom of the board (degrees Celsius)
    temp_ext_0 : float
        Temperature read from external sensor 0 (degrees Celsius) or None if
        not connected.
    temp_ext_1 : float
        Temperature read from external sensor 1 (degrees Celsius) or None if
        not connected.
    fan_0 : int
        External fan speed (RPM) of fan 0 or None if not connected.
    fan_1 : int
        External fan speed (RPM) of fan 1 or None if not connected.
    """
