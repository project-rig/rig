:py:mod:`rig.machine_control`: Machine Control APIs
===================================================

Rig provides various high-level APIs for communicating with and controlling
SpiNNaker machines. New users are encouraged to start by working through the
introductory tutorials:

.. toctree::
        :maxdepth: 2

        control_tutorials

:py:mod:`~rig.machine_control.MachineController`: SpiNNaker Control API
-----------------------------------------------------------------------

.. autoclass:: rig.machine_control.MachineController
    :members:
    :special-members:

.. automodule:: rig.machine_control.machine_controller
    :members: CoreInfo, ProcessorStatus, IPTag, MemoryIO
    :special-members:

.. automodule:: rig.machine_control.utils
    :members: sdram_alloc_for_vertices

:py:mod:`~rig.machine_control.BMPController`: BMP Control API
-------------------------------------------------------------

.. autoclass:: rig.machine_control.BMPController
    :members:
    :special-members:

.. automodule:: rig.machine_control.bmp_controller
    :members: BMPInfo, ADCInfo
    :special-members:

:py:mod:`~rig.machine_control.boot`: Low-level Machine Booting API
------------------------------------------------------------------

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


:py:mod:`~rig.machine_control.struct_file`: SC&MP Struct File Reading
---------------------------------------------------------------------

.. automodule:: rig.machine_control.struct_file
    :members:
    :special-members:

:py:mod:`~rig.machine_control.consts`: Machine and Protocol Constants
---------------------------------------------------------------------

.. automodule:: rig.machine_control.consts
    :members:
    :special-members:
