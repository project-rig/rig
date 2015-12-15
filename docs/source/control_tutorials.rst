.. py:module::rig.machine_control

Machine Control Tutorials
=========================

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

The two high-level interfaces are:

:py:class:`.MachineController`
    Interact with and control SpiNNaker chips, e.g. boot, load applications,
    read/write memory.
:py:class:`.BMPController`
    Interact with and control BMPs, e.g. control power-supplies, monitor
    system temperature, read/write FPGA registers. Only applicable to machines
    based on SpiNN-5 boards.

A tutorial for each of these interfaces is presented below.

For those wishing to extend these interfaces or directly use SCP or SDP packets,
the underlying advanced APIs are also very briefly introduced.

:py:class:`.MachineController` Tutorial
---------------------------------------

To get started, lets instantiate a :py:class:`.MachineController` which is as
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

    >>> mc.boot(12, 12)  # For a 12x12 machine
    True

If the machine could not be booted for any reason a
:py:exc:`rig.machine_control.machine_controller.SpiNNakerBootError` will be
raised. If no exception is raised, the machine is booted and ready to use. The
return value of :py:meth:`~.MachineController.boot` indicates whether the
machine was actually booted (``True``), or if it was already booted and thus
nothing was done (``False``), most applications may consider the boot to be a
success either way.

If you're using a SpiNN-2 or SpiNN-3 board booted with no further arguments,
only LED 0 will be usable. To enable the other LEDs, instead boot the machine
using one of the pre-defined boot option dictionaries in
:py:mod:`rig.machine_control.boot`, for example::

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

Writes can be optionally buffered before being transmitted to the SpiNNaker
board.  This can be configured by using the `buffer_size` keyword argument::

    >>> # Allocate 1024 bytes of SDRAM with tag '3' on chip (0, 0) with a
    >>> # 256-byte write buffer
    >>> block = mc.sdram_alloc_as_filelike(1024, 3, 0, 0, buffer_size=256)
    >>> block.buffer_size
    256

If buffering is used then
:py:meth:`~.rig.machine_control.machine_controller.MemoryIO.flush` must be
called to force writes on a given file-like (and its siblings -- see below) to
be completed::

   >>> block.seek(0)
   >>> block.write("Hello")
   >>> block.flush()

This is not necessary for unbuffered file-like objects (the default).

File-like views of memory can also be sliced to allow a single allocation to be
safely divided between different parts of the application::

    >>> hello = block[0:5]
    >>> hello.read()
    b"Hello"

Slices of the same memory file-like are considered to be siblings and flushing
one of them will result in flushing of the write buffer for all siblings.

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

:py:class:`.BMPController` Tutorial
-----------------------------------

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

Using SDP and SCP Directly (Advanced)
-------------------------------------

SCP and SDP packets can be unpacked from strings of :py:class:`bytes` received
over the network or assembled into bytes for transmission by the following two
interfaces:

* :py:class:`~.packets.SDPPacket`
* :py:class:`~.packets.SCPPacket`

A blocking implementation of SCP is provided by
:py:class:`~.scp_connection.SCPConnection`.

These are used internally by :py:class:`.MachineController` and
:py:class:`.BMPController`. Users are encouraged to read the official SDP and
SCP App-Notes and refer to the Rig source code for further guidance in using SCP
and SDP directly in applications.

.. note::
    Since different applications typically have very different requirements for
    SDP and SCP support, Rig does not currently offer any high-level support for
    their use. The developers are open to discussions about potential
    (appropriate) high-level interfaces.
