Booting a SpiNNaker machine
===========================

.. doctest::

    >>> from rig.machine_control import MachineController
    
    >>> mc = MachineController("hostname-or-ip")
    >>> mc.boot()
    True

Reference:

* :py:meth:`rig.machine_control.MachineController.boot`

Tutorial:

* :py:ref:`MachineController tutorial <MachineController-tutorial>`


Loading a SpiNNaker application
===============================

.. doctest::

    >>> from rig.machine_control import MachineController
    
    >>> mc = MachineController("hostname-or-ip")
    
    >>> # Load "app.aplx" onto cores 1, 2 and 3 of chip (0, 0) and cores 10 and
    >>> # 11 of chip (0, 1).
    >>> targets = {(0, 0): set([1, 2, 3]),
    ...            (0, 1): set([10, 11])}
    >>> mc.load_application("app.aplx", targets)
    
    >>> # Wait for the sync0 barrier, send the sync0 signal to start the
    >>> # application, wait for it to exit
    >>> mc.wait_for_cores_to_reach_state("sync0", 5)
    5
    >>> mc.send_signal("sync0")
    >>> mc.wait_for_cores_to_reach_state("exit", 5)
    5
    
    >>> # Clean up!
    >>> mc.send_signal("stop")

Reference:

* :py:meth:`rig.machine_control.MachineController.load_application`
* :py:meth:`rig.machine_control.MachineController.wait_for_cores_to_reach_state`
* :py:meth:`rig.machine_control.MachineController.send_signal`

Tutorial:

* :py:ref:`MachineController tutorial <MachineController-tutorial>`


Real-time communication via Ethernet using SDP
==============================================

.. doctest::

    >>> import socket
    >>> from rig.machine_control import MachineController
    >>> from rig.machine_control.packets import SCPPacket
    
    >>> # Open a UDP socket to receive packets on
    >>> in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    >>> in_sock.bind(("", 50007))
    >>> addr, port = in_sock.getsockname()
    
    >>> # Set-up IP Tag 1 on chip (0, 0) to forward SDP packets the UDP socket
    >>> mc = MachineController("spinnaker-machine-hostname")
    >>> mc.iptag_set(1, addr, port, 0, 0)
    
    >>> # Start receiving packets from an application running on SpiNNaker
    >>> while True:
    ...     print(SCPPacket.from_bytestring(self.in_sock.recv(512)))

Reference:

* :py:mod:`socket`
* :py:meth:`rig.machine_control.MachineController.iptag_set`
* :py:class:`rig.machine_control.packets.SCPPacket`

Tutorial:

* :py:ref:`scp-and-sdp-tutorial`
