.. py:module::rig.machine_control

.. _control-tutorials:

Tutorial: Controlling SpiNNaker machines
========================================

SpiNNaker machines consist of a network of SpiNNaker chips and, in larger
systems, a set of Board Management Processors (BMPs) which control and monitor
systems' power and temperature. SpiNNaker (and BMPs) are controlled using `SCP`_
packets (a protocol built on top of `SDP`_) sent over the network to a machine.
Rig includes a set of high-level wrappers around the low-level SCP commands
which are tailored towards SpiNNaker application developers.


.. _SCP: https://spinnaker.cs.man.ac.uk/tiki-download_wiki_attachment.php?attId=17&page=Application%20note%205%20-%20SCP%20Specification&download=y

.. _SDP: https://spinnaker.cs.man.ac.uk/tiki-download_wiki_attachment.php?attId=16&page=Application%20note%204%20-%20SDP%20Specification&download=y

.. note::
    Rig does not aim to provide a complete Python implementation of the full
    (low-level) SCP command set. Users who encounter missing functionality as a
    result of this are encouraged to submit a patch or open an issue as the
    developers are open to (reasonable) suggestions!

In addition to these high-level interfaces, Rig includes a lower-level
interface for sending and receiving application-defined SDP and SCP packets to
running applications via a socket.

The two high-level machine control interfaces are:

:py:class:`.MachineController`
    Interact with and control SpiNNaker chips, e.g. boot, load applications,
    read/write memory.
:py:class:`.BMPController`
    Interact with and control BMPs, e.g. control power-supplies, monitor
    system temperature, read/write FPGA registers. Only applicable to machines
    based on SpiNN-5 boards.

The low-level SDP and SCP interfaces are:

:py:class:`~rig.machine_control.packets.SDPPacket`
    Pack and unpack SDP packets.
:py:class:`~rig.machine_control.packets.SCPPacket`
    Pack and unpack SCP packets.

A tutorial for each of these interfaces is presented below.

.. _MachineController-tutorial:

:py:class:`.MachineController`
------------------------------

To get started, let's instantiate a :py:class:`.MachineController`. This is as
simple as giving the hostname or IP address of the machine::

    >>> from rig.machine_control import MachineController
    >>> mc = MachineController("spinnaker_hostname")

.. note::
    If you're using a multi-board machine, give the hostname of the (0, 0) chip.
    Support for connecting to multiple Ethernet ports of a SpiNNaker machine is
    not currently available but should be automatic. 

Booting
^^^^^^^

You can :py:meth:`~.MachineController.boot` the system like so::

    >>> mc.boot()
    True

If the machine could not be booted for any reason a
:py:exc:`rig.machine_control.machine_controller.SpiNNakerBootError` will be
raised. If no exception is raised, the machine is booted and ready to use. The
return value of :py:meth:`~.MachineController.boot` indicates whether the
machine was actually booted (``True``), or if it was already booted and thus
nothing was done (``False``), most applications may consider the boot to be a
success either way.

If you're using a SpiNN-2 or SpiNN-3 board booted without arguments, only LED 0
will be usable. To enable the other LEDs, instead boot the machine using one of
the pre-defined boot option dictionaries in :py:mod:`rig.machine_control.boot`,
for example::

    >>> from rig.machine_control.boot import spin3_boot_options
    >>> mc.boot(**spin3_boot_options)
    True

Probing for Available Resources
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :py:meth:`~.MachineController.get_system_info` method returns a
:py:class:`~rig.machine_control.machine_controller.SystemInfo` object
describing which chips, links and cores are alive and also the SDRAM
available::

    >>> system_info = mc.get_system_info()

This object can also be used to guide Rig's place and route utilities (see
:py:class:`rig.place_and_route.place_and_route_wrapper`,
:py:class:`rig.place_and_route.utils.build_machine` and
:py:class:`rig.place_and_route.utils.build_core_constraints`).

Loading Applications
^^^^^^^^^^^^^^^^^^^^

The :py:meth:`~.MachineController.load_application` method will,
unsurprisingly, load an application onto an arbitrary set of SpiNNaker cores.
For example, the following code loads the specified APLX file to cores 1, 2 and
3 of chip (0, 0) and cores 10 and 11 of chip (0, 1)::

    >>> targets = {(0, 0): set([1, 2, 3]),
    ...            (0, 1): set([10, 11])}
    >>> mc.load_application("/path/to/app.aplx", targets)

Alternatively, this method accepts dictionaries mapping applications to
targets, such as those produced by
:py:class:`rig.place_and_route.place_and_route_wrapper`.

:py:meth:`~.MachineController.load_application` verifies that all applications
have been successfully loaded (re-attempting a small number of times if
necessary). If not all applications could be loaded, a
:py:exc:`~rig.machine_control.machine_controller.SpiNNakerLoadingError`
exception is raised.

Many applications require the `sync0` signal to be sent to start the
application's event handler after loading. We can wait for all cores to reach
the `sync0` barrier using
:py:class:`~.MachineController.wait_for_cores_to_reach_state` and then send the
`sync0` signal using :py:class:`~.MachineController.send_signal`::

    >>> # In the example above we loaded 5 cores so we expect 5 cores to reach
    >>> # sync0.
    >>> mc.wait_for_cores_to_reach_state("sync0", 5)
    5
    >>> mc.send_signal("sync0")

Similarly, after application execution, the application can be killed with::

    >>> mc.send_signal("stop")

Since the stop signal also cleans up allocated resources in a SpiNNaker machine
(e.g. stray processes, routing entries and allocated SDRAM), it is desirable
for this signal to reliably get sent even if something crashes in the host
application. To facilitate this, you can use the
:py:meth:`~.MachineController.application` context manager::

    >>> with mc.application():
    ...     # Main application code goes here, e.g. loading applications,
    ...     # routing tables and SDRAM.
    >>> # When the above block exits (even if due to an exception), the stop
    >>> # signal will be sent to the application.

.. note::
    Many application-oriented methods accept an `app_id` argument which is given
    a sensible default value. If the :py:meth:`.MachineController.application`
    context manager is given an app ID as its argument, this app ID will become
    the default `app_id` within the `with` block. See the section on context
    managers below for more details.

Loading Routing Tables
^^^^^^^^^^^^^^^^^^^^^^

Routing table entries can be loaded using
:py:meth:`~.MachineController.load_routing_tables` like so::

    >>> routing_tables = {
    ...     (0, 0): [RoutingTableEntry(...), ...],
    ...     (0, 1): [RoutingTableEntry(...), ...],
    ...     ...
    ... }
    >>> mc.load_routing_tables(routing_tables)

This command allocates and then loads the requested routing table entries onto
each of the supplied chips. The supplied data structure matches that produced by
:py:func:`rig.place_and_route.place_and_route_wrapper`.

Allocating/Writing/Reading SDRAM
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Many SpiNNaker applications require the writing and reading of large blocks of
SDRAM data. The recommended way of doing this is to allocate blocks of SDRAM
using :py:meth:`~.MachineController.sdram_alloc` with an identifying 'tag'. The
The SpiNNaker application can later use this tag number to look up the address
of the allocated block of SDRAM. Not only does this avoid the need to
explicitly communicate SDRAM locations to the application it also allows SARK
to safely allocate memory in the SDRAM.

:py:meth:`~.MachineController.read` and :py:meth:`~.MachineController.write`
methods are provided which can read and write arbitrarily large blocks of data
to and from memory in SpiNNaker::

    >>> # Allocate 1024 bytes of SDRAM with tag '3' on chip (0, 0)
    >>> block_addr = mc.sdram_alloc(1024, 3, 0, 0)
    >>> mc.write(block_addr, b"Hello, world!")
    >>> mc.read(block_addr, 13)
    b"Hello, world!"

Rig also provides a file-like I/O wrapper
(:py:class:`~rig.machine_control.machine_controller.MemoryIO`) which may prove
easier to integrate into applications and also ensures reads and writes are
constrained to the allocated region. ::

    >>> # Allocate 1024 bytes of SDRAM with tag '3' on chip (0, 0)
    >>> block = mc.sdram_alloc_as_filelike(1024, 3, 0, 0)
    >>> block.write(b"Hello, world!")
    >>> block.seek(0)
    >>> block.read(13)
    b"Hello, world!"

File-like views of memory can also be sliced to allow a single allocation to be
safely divided between different parts of the application::

    >>> hello = block[0:5]
    >>> hello.read()
    b"Hello"

The :py:func:`~rig.machine_control.utils.sdram_alloc_for_vertices` utility
function is provided to allocate multiple SDRAM blocks simultaneously.  This
will be especially useful if you're using Rig's :doc:`place and route
tools<place_and_route>`, since the utility accepts the place-and-route tools'
output format. For example::

    >>> placements, allocations, application_map, routing_tables = \
    ...     rig.place_and_route.wrapper(...)
    >>> from rig.machine_control.utils import sdram_alloc_for_vertices
    >>> vertex_memory = sdram_alloc_for_vertices(mc, placements, allocations)
    
    >>> # The returned dictionary maps from vertex to file-like wrappers
    >>> vertex_memory[vertex].write(b"Hello, world!")


Context Managers
^^^^^^^^^^^^^^^^

Many methods of :py:class:`~.MachineController` require arguments such as `x`,
`y`, `p` or `app_id` which can quickly lead to repetitive and messy code. To
reduce the repetition Python's ``with`` statement can be used::

    >>> # Within the block, all commands will affect chip (1, 2)
    >>> with mc(x = 1, y = 2):
    ...     block_addr = mc.sdram_alloc(1024, 3)
    ...     mc.write(block_addr, b"Hello, world!")


.. _BMPController-tutorial:

:py:class:`.BMPController`
--------------------------

A limited set of utilities are provided for interacting with SpiNNaker BMPs
which are contained in the :py:class:`.BMPController` class. In systems with
either a single SpiNN-5 board or a single frame of SpiNN-5 boards which are
connected via a backplane, the class can be constructed like so::

    >>> from rig.machine_control import BMPController
    >>> bc = BMPController("bmp_hostname")

For larger systems which contain many frames of SpiNNaker boards, at least one
IP address or hostname must be specified for each::

    >>> bc = BMPController({
    ...     # At least one hostname per rack is required
    ...     (0, 0): "cabinet0_frame0_hostname",
    ...     (0, 1): "cabinet0_frame1_hostname",
    ...     ...
    ...     (1, 0): "cabinet1_frame0_hostname",
    ...     (1, 1): "cabinet1_frame1_hostname",
    ...     ...
    ...     # Individual boards can be given their own unique hostname if
    ...     # required which overrides those above
    ...     (1, 1, 0): "cabinet1_frame1_board0_hostname",
    ... })

Boards are referred to by their (cabinet, frame, board) coordinates::

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

Power Control
^^^^^^^^^^^^^

Boards can be powered on using :py:meth:`~.BMPController.set_power`::

    >>> # Power off board (0, 0, 0)
    >>> bc.set_power(False)
    
    >>> # Power on board (1, 2, 3)
    >>> bc.set_power(True, 1, 2, 3)
    
    >>> # Power on all 24 boards in frame (1, 2)
    >>> bc.set_power(True, 1, 2, range(24))

.. note::
    Though multiple boards in a single frame can be powered on simultaneously,
    boards in different frames must be powered on separately.

.. note::
    By default the :py:meth:`~.BMPController.set_power` method adds a delay
    after the power on command has completed to allow time for the SpiNNaker
    cores to complete their self tests. If powering on many frames of boards,
    the `post_power_on_delay` argument can be used to reduce or eliminate this
    delay.

Reading Board Temperatures
^^^^^^^^^^^^^^^^^^^^^^^^^^

Various information about a board's temperature and power supplies can be read
using :py:meth:`~.BMPController.read_adc` (ADC = Analogue-to-Digital Converter)
which returns a :py:class:`.bmp_controller.ADCInfo` named tuple containing many
useful values::

    >>> adc_info = bc.read_adc()  # Get info for board (0, 0, 0)
    >>> adc_info.temp_top  # Celsius
    23.125
    >>> adc_info.fan_0  # RPM (or None if not attached)
    2401

Context Managers
^^^^^^^^^^^^^^^^

As with :py:class:`.MachineController`, :py:class:`.BMPController` supports the
``with`` syntax for specifying common arguments to a series of commands::

    >>> with bc(cabinet=1, frame=2, board=3):
    ...     if bc.read_adc().temp_top > 75.0:
    ...         bc.set_led(7, True)  # Turn on LED 7 on the board


.. _scp-and-sdp-tutorial:

Sending/receiving SDP and SCP packets to/from applications
----------------------------------------------------------

A number of low-level facilities are provided for users who wish to send and
receive SCP and SDP packets directly. The most common use for these APIs is to
send and receive SDP packets to and from a running SpiNNaker application to
allow realtime monitoring and communication with the underlying application via
an IP Tag. A minimal example of each is presented below.

Example: Sending SDP packets to a running application
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In your SpiNNaker application you should register a callback handler for the
arrival of SDP packets. For example, using the ``spin1_api``:

.. code-block:: c

    spin1_callback_on(SDP_PACKET_RX, on_sdp_from_host, 0);

To send SDP packets to this application, you must open a UDP socket with which
to send SDP packets to your SpiNNaker system. Note that (slightly confusingly)
SpiNNaker listens for incoming SDP packets on the :py:data:`SCP port
<rig.machine_control.consts.SCP_PORT>`.

::

    >>> import socket
    >>> from rig.machine_control.consts import SCP_PORT
    >>> out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    >>> out_sock.connect((hostname, SCP_PORT))

With the port opened, you can use the
:py:class:`rig.machine_control.packets.SDPPacket` and
:py:class:`rig.machine_control.packets.SCPPacket` classes to pack your data
into properly formatted SDP or SCP packets. Since ``sark`` and ``spin1_api``
(unfortunately) make packing/unpacking SDP packets rather clumsy it is common
to use SCP packets. 

.. note::

    SCP packets are just SDP packets with some additional fields placed in the
    SDP data payload. When a port number other than 0 is used SCP packets are
    passed to the application like any other SDP packet

As an example, to send an SCP packet core 1 on chip (0, 0) with a ``cmd_rc`` of
``123``::

    >>> from rig.machine_control.packets import SCPPacket
    >>> data = b"Hello world!\0"
    >>> packet = SCPPacket(
    ...     dest_port=1,
    ...     dest_x=0, dest_y=0, dest_cpu=1,
    ...     cmd_rc=123
    ...     data=data
    ... )
    >>> out_sock.send(packet.bytestring)

On the receiving core the ``on_sdp_from_host`` callback might then look like
this:

.. code-block:: c

    void on_sdp_from_host(uint mailbox, uint port)
    {
      sdp_msg_t *msg = (sdp_msg_t *)mailbox;
      if (msg->cmd_rc == 123)
      {
        io_printf(IO_BUF,
                  "Got SCP packet from host with data: %s\n",
                  msg->data);
      }
      spin1_msg_free(msg);
    }

.. note::

    SpiNNaker can only receive packets up to a certain size. This size can be
    determined using :py:class:`~rig.machine_control.MachineController`'s
    :py:meth:`~rig.machine_control.MachineController.scp_data_length` property
    This property defines the maximum length of the data-field in an SCP packet
    sent to the machine.


Example: Receiving SDP packets from a running application
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To receive SDP packets from an application there must first be an open socket
ready to receive the packets. For example::

    >>> import socket
    >>> PORT = 50007
    >>> in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    >>> in_sock.bind(("", PORT))

Next, you must set up an 'IP tag' on every Ethernet-connected SpiNNaker chip
through which SDP packets may be sent back to the host which informs SpiNNaker
of the IP address these packets should be sent to.

A list of the Ethernet-connected chips in a typical SpiNNaker machine can be
produced using
:py:class:`rig.machine_control.MachineController.get_system_info` and an IP tag
configured on each using
:py:class:`rig.machine_control.MachineController.iptag_set` like so::

    >>> from rig.machine_control import MachineController
    
    >>> # Get the IP and port of the socket we opened
    >>> addr, port = in_sock.getsockname()
    
    >>> # Set-up IP Tag 1 on each ethernet-connected chip to forward all SDP
    >>> # packets to this socket.
    >>> mc = MachineController("spinnaker-machine-hostname")
    >>> si = mc.get_system_info()
    >>> for (x, y), chip_ip in si.ethernet_connected_chips():
    ...     mc.iptag_set(1, addr, port, x, y)

You can now listen for incoming packets and unpack them using
:py:meth:`rig.machine_control.packets.SDPPacket.from_bytestring` and
:py:meth:`rig.machine_control.packets.SCPPacket.from_bytestring`. For example,
to unpack SCP packets received from the machine::

    >>> from rig.machine_control.packets import SCPPacket
    >>> while True:
    ...     data = self.in_sock.recv(512)
    ...     if not data:
    ...         break
    ...     packet = SCPPacket.from_bytestring(data)
    ...     print("Got SCP packet from core {packet.src_cpu} "
    ...           "of chip ({packet.src_x}, {packet.src_y}) "
    ...           "with cmd_rc {packet.cmd_rc} and data "
    ...           "{packet.data}.".format(packet=packet))

.. note::

    We use a 512 byte UDP receive buffer since at present the largest SDP
    packet supported by the machine at the time of writing is 256 bytes + 24
    bytes SCP header. Using power-of-two sized receive buffers is recommended
    on most operating systems for performance reasons. The
    :py:class:`~rig.machine_control.MachineController`'s
    :py:meth:`~rig.machine_control.MachineController.scp_data_length` property
    can be used to get the actual value.

SCP packets might be sent from a SpiNNaker application using code such as:

.. code-block:: c

    sdp_msg_t msg;
    
    void send_scp_packet(const char *data)
    {
      // Send to the nearest Ethernet-connected chip.
      msg.tag = 1;
      msg.dest_port = PORT_ETH;
      msg.dest_addr = sv->eth_addr;

      // Indicate the packet's origin as this chip/core. Note that the core is
      // indicated in the bottom 5 bits of the srce_port field.
      msg.flags = 0x07;
      msg.srce_port = spin1_get_core_id();
      msg.srce_addr = spin1_get_chip_id();
      
      // Copy the supplied data into the data field of the packet and update
      // the length accordingly.
      int len = strlen(data) + 1;  // Include the null-terminating byte
      spin1_memcpy(msg.data, (void *)data, len);
      msg.length = sizeof (sdp_hdr_t) + sizeof (cmd_hdr_t) + len;

      // and send it with a 100ms timeout
      spin1_send_sdp_msg(&msg, 100);
    }

