from six import iteritems, next, itervalues

from .scp_connection import SCPConnection

from rig.utils.contexts import ContextMixin, Required


class BMPController(ContextMixin):
    """Control the BMPs (Board Management Processors) onboard SpiNN-4 and
    SpiNN-5 boards in a SpiNNaker machine.

    BMPs (and thus boards) are addressed as follows::
    
                  2             1                0
        Rack -----+-------------+----------------+
                  |             |                |
        +-------------+  +-------------+  +-------------+   Sub-Rack
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
                 Boards ----+-+-+-+-+
                            4 3 2 1 0
    
    Coordinates are conventionally written as 3-tuples of integers (rack,
    subrack, board). This gives the upper-right-most board's coordinate (0, 0,
    0).
    
    Communication with BMPs is facilitated either via Ethernet or via the CAN
    bus within each subrack.
    """
    
    def __init__(self, hosts, n_tries=5, timeout=0.5,
                 initial_context={rack: 0, subrack: 0, board: 0}):
        """Create a new controller for BMPs in a SpiNNaker machine.

        Parameters
        ----------
        hosts : string or {coord: string, ...}
            Hostname or IP address of the BMP to connect to or alternatively,
            multiple addresses can be given in a dictionary to allow control of
            many boards. `coord` may be given as ether (rack, subrack) or
            (rack, subrack, board) tuples. In the former case, the address will
            be used to communicate with all boards in the specified subrack
            except those listed explicitly. If only a single hostname is
            supplied it is assumed to be for all boards in rack 0, subrack 0.
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
            hosts = 
        else:
            hosts = hosts
        assert len(set(itervalues(hosts))) == len(hosts), \
            "All hosts must have unique hostname/IP address."
        self.connections = {
            coord: SCPConnection(host, n_tries, timeout)
            for coord, host in iteritems(hosts)
        }

    @property
    def scp_data_length(self):
        if self._scp_data_length is None:
            # Select an arbitrary host to send an sver to (preferring
            # fully-specified hosts)
            host = max(hosts, key=len)
            if len(host) == 2:
                host = (host[0], host[1], 0)
            data = self.get_software_version(*host)
            self._scp_data_length = data.buffer_size
        return self._scp_data_length
    
    
    def __call__(self, **context_args):
        """Create a new context for use with `with`."""
        return self.get_new_context(**context_args)
    
    
    @ContextMixin.use_named_contextual_arguments(
        rack=Required, subrack=Required, board=Required)
    def send_scp(self, *args, **kwargs):
        """Transmit an SCP Packet to a specific board.

        See the arguments for
        :py:method:`~rig.machine_control.scp_connection.SCPConnection` for
        details.
        """
        # Retrieve contextual arguments from the keyword arguments.  The
        # context system ensures that these values are present.
        rack = kwargs.pop("rack")
        subrack = kwargs.pop("subrack")
        board = kwargs.pop("board")
        return self._send_scp(rack, subrack, board, *args, **kwargs)

    def _send_scp(self, rack, subrack, board, *args, **kwargs):
        """Determine the best connection to use to send an SCP packet and use
        it to transmit.

        See the arguments for
        :py:method:`~rig.machine_control.scp_connection.SCPConnection` for
        details.
        """
        # Find the connection which best matches the specified coordinates,
        # preferring direct connections to a board when available.
        connection = self.connections.get((rack, subrack, board), None)
        if connection is None:
            connection = self.connections.get((rack, subrack), None)
        assert connection is not None, \
            "No connection available to ({}, {}, {})".format(rack,
                                                             subrack,
                                                             board)
        return connection.send_scp(0, 0, board, *args, **kwargs)
    
    
    @ContextMixin.use_contextual_arguments
    def get_software_version(self, rack=Required, subrack=Required,
                             board=Required):
        """Get the software version for a given BMP.

        Returns
        -------
        :py:class:`CoreInfo`
            Information about the software running on a BMP.
        """
        sver = self._send_scp(rack, subrack, board, SCPCommands.sver)

        # Format the result
        # arg1 => p2p address, physical cpu, virtual cpu
        p2p = sver.arg1 >> 16
        pcpu = (sver.arg1 >> 8) & 0xff
        vcpu = sver.arg1 & 0xff

        # arg2 => version number and buffer size
        version = (sver.arg2 >> 16) / 100.
        buffer_size = (sver.arg2 & 0xffff)

        return CoreInfo(p2p, pcpu, vcpu, version, buffer_size, sver.arg3,
                        sver.data)
