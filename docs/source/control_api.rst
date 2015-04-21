Machine Control API Documentation
=================================

The documentation below covers the main parts of Rig's machine control libraries
however some low-level components are omitted for brevity. Advanced users are
referred to the (heavily documented) code itself where required.

SpiNNaker Control API
---------------------

.. autoclass:: rig.machine_control.MachineController
    :members:
    :special-members:

.. automodule:: rig.machine_control.machine_controller
    :members: CoreInfo, ProcessorStatus, IPTag, MemoryIO
    :special-members:

.. automodule:: rig.machine_control.utils
    :members: sdram_alloc_for_vertices

BMP Control API
---------------

.. autoclass:: rig.machine_control.BMPController
    :members:
    :special-members:

.. automodule:: rig.machine_control.bmp_controller
    :members: BMPInfo, ADCInfo
    :special-members:

Boot API
--------

.. automodule:: rig.machine_control.boot
    :members:
    :special-members:
    :exclude-members: boot_packet, BootCommand

Advanced SCP/SDP APIs
---------------------

:py:mod:`~rig.machine_control.packets`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: rig.machine_control.packets
    :members:
    :special-members:


:py:mod:`~rig.machine_control.scp_connection`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: rig.machine_control.scp_connection
    :members:
    :special-members:


Struct File Reading
-------------------

.. automodule:: rig.machine_control.struct_file
    :members:
    :special-members:

Constant Definitions
--------------------

.. automodule:: rig.machine_control.consts
    :members:
    :special-members:

