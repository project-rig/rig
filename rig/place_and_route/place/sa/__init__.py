"""An experimental simulated-annealing based placer.

The annealing algorithm is broken into two components: the high-level algorithm
implementation :py:func:`~rig.place_and_route.place.sa.place` and a simulated
annealing placement :py:class:`~rig.place_and_route.place.sa.kernel.Kernel`.

The algorithm takes care of initial placement, handles special-case "trivial"
placement problems where no placer effort is requried, handles details of
:py:mod:`~rig.place_and_route.constraints`, and manages the annealing scheudle.

The kernel is responsible for performing the kernel of the annealing operation:
swapping vertices, evaluating the change in cost and reverting (some) bad
swaps. Since this is the most performance-sensitive part of the algorithm, its
implementation may be swapped for more efficient implementations as required. A
portable, but slow, kernel written in Python is included in
:py:class:`~rig.place_and_route.place.sa.python_kernel.PythonKernel`.
"""

from rig.place_and_route.place.sa.algorithm import place
