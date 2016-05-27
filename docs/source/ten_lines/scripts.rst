Discover an unbooted SpiNNaker board's IP address
=================================================

Via the command-line:

..
    
    $ rig-discover
    192.168.240.253

From Python:

.. doctest::

    >>> from rig.machine_control.unbooted_ping import listen
    >>> listen()
    "192.168.240.253"

Refrerence:

* :py:func:`rig.machine_control.unbooted_ping.listen`
* :ref:`rig-discover`

Discover if your application is dropping packets
================================================

..
    
    $ rig-counters HOSTNAME --command python my_application.py HOSTNAME
    time,dropped_multicast
    10.4,102

Our application took 10.4 seconds to execute and dropped 102 multicast packets
in total.

Tutorial:

* :ref:`rig-counters`
