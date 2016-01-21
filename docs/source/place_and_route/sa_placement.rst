Simulated Annealing Based Placement
===================================

.. automodule:: rig.place_and_route.place.sa

Kernel Prototype
----------------

All kernel implementations should obey the following interface:

.. autoclass:: rig.place_and_route.place.sa.kernel.Kernel
    :members:
    :special-members:

Available Kernels
-----------------

.. autoclass:: rig.place_and_route.place.sa.python_kernel.PythonKernel

.. autoclass:: rig.place_and_route.place.sa.c_kernel.CKernel
