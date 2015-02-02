"""A collection of utilities for mapping a hyper-graph (vertices and nets) to a
SpiNNaker machine.

The task is split into two phases: placing and routing. During placement each
vertex is allocated a specific chip in a SpiNNaker machine.  During routing,
multicast routes are generated between the chips on which nets' vertices have
been placed.

It is worth emphasising that every vertex is placed on *exactly one chip*. A
chip may be allocated many vertices. Each vertex is associated with a set of
(user-defineable) resources, for example Cores or SDRAM space. Simillarly,
chips are defined as having a finite quantity of each of these resources. The
placement algorithm will attempt to find an allocation of vertices to chips
such that no resource is over-allocated.

Place and Route Algorithms
--------------------------
The general place and route problem is NP-hard and so this module contains a
number of complementary place and route algorithms with a common interface
enabling the user to trade-off runtime against solution quality.


Resources and Cores
-------------------
Resources may be completely user-defined quantities however most applications
will use (possibly a subset of) those defined in the `resources` submodule.  As
you will see `Cores` are thus just a standard per-chip resource. A vertex may
consume one or more cores however since a vertex is assigned to exactly one
chip, it cannot consume more cores than are available on a single chip and will
never be split across chips. Users should be careful when using a number of
cores greater than one that they *really* intend to specify that a vertex must
be placed on multiple cores on a single chip. A typical use for vertices which
consume no cores are external peripherals. Such vertices will typically further
be subjected to placement constraints: see the `constraints` submodule for
more.
"""

from .resources import Cores, SDRAM, SRAM
from .links import Links

from .machine import Machine
