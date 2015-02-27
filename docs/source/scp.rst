Controlling a SpiNNaker machine using the SCP protocol
######################################################

The SCP protocol is used to communicate with running SpiNNaker machines.
A simple implementation of SCP is provided in the `rig.communicator` module.
This implementation uses stop-and-wait flow-control to limit the rate at which packets are
transmitted across the network.

To communicate with a given SpiNNaker machine one creates an :py:class:`~rig.machine_control.MachineController`.

.. autoclass:: rig.machine_control.MachineController
        :members:
        :special-members:
