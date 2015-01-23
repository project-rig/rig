Controlling a SpiNNaker machine using the SCP protocol
######################################################

The SCP protocol is used to communicate with running SpiNNaker machines.
A simple implementation of SCP is provided in the `rig.communicator` module.
This implementation uses stop-and-wait flow-control to limit the rate at which packets are
transmitted across the network.

To communicate with a given SpiNNaker machine one creates an :py:class:`~rig.communicator.SCPCommunicator`.

.. autoclass:: rig.communicator.SCPCommunicator
        :members: __init__

Reading and writing SpiNNaker memory
====================================

The methods :py:func:`~rig.communicator.SCPCommunicator.read` and
:py:func:`~rig.communicator.SCPCommunicator.write` can be used to read or write
up-to 256 bytes of memory at a time.  Bytestrings are the standard
representation for values.  A more file-like interface is provided by
:py:class:`~rig.communicator.SDRAMFile`

Data types are instances of :py:class:`~rig.communicator.DataType`

.. autoclass:: rig.communicator.DataType
        :members: BYTE, SHORT, WORD

.. automethod:: rig.communicator.SCPCommunicator.read

.. automethod:: rig.communicator.SCPCommunicator.write

File-like interface
-------------------

.. autoclass:: rig.communicator.SDRAMFile
        :members: __init__, read, write, seek, tell, address

Booting a board
===============

Loading and controlling applications
====================================

Manipulating the board state
============================

LEDs
----
.. automethod:: rig.communicator.SCPCommunicator.set_led

IP Tags
-------
.. automethod:: rig.communicator.SCPCommunicator.iptag_set
.. automethod:: rig.communicator.SCPCommunicator.iptag_get
.. automethod:: rig.communicator.SCPCommunicator.iptag_clear
