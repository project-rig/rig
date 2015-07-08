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

For example, to power cycle a SpiNN-5 board (or a 24-board frame there-of)::

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
