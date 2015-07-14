``rig-boot``
============

The ``rig-boot`` command lets you quickly and easily boot SpiNNaker systems
from the command line.

For example, to boot a SpiNN-3 board::

    $ rig-boot HOSTNAME --spin3

Or to boot a large SpiNNaker machine comprising many boards::

    $ rig-boot HOSTNAME WIDTH HEIGHT

To get a complete listing of available options and supported SpiNNaker boards,
type::

    $ rig-boot --help

``rig-power``
=============

The ``rig-power`` command lets you quickly and easily power on and off
SpiNNaker systems consisting of SpiNN-5 boards via their Board Management
Processors (BMP).

For example, to power cycle a SpiNN-5 board (or a 24-board frame thereof)::

    $ rig-power BMP_HOSTNAME

To power-off::

    $ rig-power BMP_HOSTNAME off

To power-cycle board 3 and the last 12 boards in frame::

    $ rig-power BMP_HOSTNAME -b 3,12-23

To get a complete listing of available options::

    $ rig-power --help

``rig-info``
============

The ``rig-info`` command displays basic information about (booted) SpiNNaker
systems and BMPs. The command accepts a single hostname as an argument and
prints output such as the following::

    $ rig-info SPINNAKER_BOARD_HOSTNAME
    Device Type: SpiNNaker
    
    Software: SC&MP v1.33 (Built 2014-09-24 11:32:23)
    
    Machine dimensions: 8x8
    Working chips: 48 (18 cores: 40, 17 cores: 8)
    Network topology: mesh
    Dead links: 0 (+ 48 to dead/missing cores)
    
    Application states:
        scamp-133: 48 run
        sark: 808 idle

And for BMPs::

    $ rig-info BMP_HOSTNAME
    Device Type: BMP
    
    Software: BC&MP v1.36 (Built 2014-09-15 10:24:15)
    Code block in use: 1
    Board ID (slot number): 0
    
    1.2 V supply: 1.24 V, 1.24 V, 1.24 V
    1.8 V supply: 1.81 V
    3.3 V supply: 3.32 V
    Input supply: 11.98 V
    
    Temperature top: 28.9 *C
    Temperature bottom: 30.0 *C


``rig-discover``
================

The ``rig-discover`` command listens for any attached unbooted SpiNNaker
boards on the network. This can be used to determine the IP address of a
locally attached board. Example::

    $ rig-discover
    192.168.240.253

If no machines are discovered, the command will exit after a short timeout
without printing anything.


``rig-iobuf``
================

The ``rig-iobuf`` command prints the messages printed by an application's calls
to ``io_printf(IOBUF, ...)``. For example, printing the IOBUF for core 1 on
chip 0, 0::

    $ rig-iobuf HOSTNAME 0 0 1
    Hello, world!


``rig-ps``
================

The ``rig-ps`` command enumerates every application running on a machine. For
example::

    $ rig-ps HOSTNAME
    X   Y   P   State             Application      App ID
    --- --- --- ----------------- ---------------- ------
      0   0   0 run               scamp-133             0
      0   0   1 sync0             network_tester       66
      0   0   2 sync0             network_tester       66
      0   0   3 sync0             network_tester       66
      0   0   4 sync0             network_tester       66
      0   0   5 sync0             network_tester       66
    ...snip...

The listing can be filtered by:

* Application ID with ``--app-id`` or ``-a``
* Application name with ``--name`` or ``-n``
* Application State with ``--state`` or ``-s``

The above arguments accept regular expressions as their argument. These can be
used, for example, to locate misbehaving application cores::

    $ rig-ps HOSTNAME --state '(?!run)'
    X   Y   P   State             Application      App ID
    --- --- --- ----------------- ---------------- ------
      3   6  13 watchdog          network_tester       66

Finally, the listings can be carried out for just a particular chip or core by
adding the optional 'x', 'y' and 'p' arguments (similar to the ybug 'ps'
command)::

    $ rig-ps HOSTNAME 0 0 3
    X   Y   P   State             Application      App ID
    --- --- --- ----------------- ---------------- ------
      0   0   3 sync0             network_tester       66


``rig-counters``
================

The ``rig-counters`` command reads the router diagnostic counters for all chips
in a SpiNNaker system and reports any changes in value. This can be useful, for
example, when checking if (and where) an application is dropping packets.

In the simplest use case, simply call ``rig-counters`` with a SpiNNaker
hostname as an argument, run your application and then press enter to see how
many packets were dropped::

    $ rig-counters HOSTNAME
    time,dropped_multicast
    <press enter>
    8.7,234

In the example above, 234 packets were dropped. Note that the output is in the
form of a CSV file. You can give the `--multiple`` option to allow multiple
samples to be captured. In the example below we capture four samples::

    $ rig-counters HOSTNAME --multiple > out.csv
    <press enter>
    <press enter>
    <press enter>
    <press enter>
    <press enter> ^C
    $ cat out.csv
    time,dropped_multicast
    1.0,12
    1.4,34
    2.3,23
    2.7,11

Instead of manually pressing enter to trigger a sample, you can use the
``--command`` argument to report the number of dropped packets during the
execution of your program::

    $ rig-counters HOSTNAME --command ./my_program my_args
    time,dropped_multicast
    10.4,102

You can also report each router's counter values individually using the
``--detailed`` option::

    $ rig-counters HOSTNAME --detailed
    time,x,y,dropped_multicast
    <press enter>
    10.4,0,0,10
    10.4,0,1,2
    10.4,0,2,5
    ...

Other router counter values can be reported too, see ``rig-counters --help``
for more details.

.. warning::

    ``rig-counters`` works by polling the router in every chip in a SpiNNaker
    machine. This process takes some time (i.e. it isn't monotonic) and also
    results in P2P messages being sent through the SpiNNaker network.

    The system is polled once when the utility is started and then once more
    for each sample requested (e.g. every time you press enter). As a result,
    you should be careful to only start or trigger a poll when the machine is
    otherwise idle, for example, before or after your application runs.
