"""A collection of utilities for controlling the operation of a SpiNNaker
machine.

SpiNNaker software and board management processors (BMPs) can be controlled
through the use of the SpiNNaker Control Protocol (SCP).  A
:py:class:`~MachineController` wraps up these interfaces and provides
higher-level methods to fulfil various machine-management tasks.  Further
classes are provided to manipulate SpiNNaker Datagram Protocol (SDP) and SCP
packets directly, and a stop-and-wait implementation of SCP.

General usage
=============

Often it will be sufficient to instantiate and use a
:py:class:`~MachineController` to boot a SpiNNaker machine and control the
execution of applications upon it.  The MachineController converts high-level
commands into SCP packet(s) which are multiplexed over as many ethernet
connections as it is aware of.  As the SCP implementation used is blocking,
latency is best reduced by ensuring that SCP packets enter the SpiNNaker
machine at the ethernet connection nearest their destination chip.

Representing SCP and SDP packets
================================

SCP and SDP packets can be extracted from strings of :py:class:`bytes` received
over the network or assembled into bytes for transmission.

See:
    * :py:class:`~SDPPacket`
    * :py:class:`~SCPPacket`

A blocking implementation of SCP is provided by
:py:class:`~.scp_connection.SCPConnection`.
"""
from .packets import SCPPacket, SDPPacket
from .machine_controller import MachineController
