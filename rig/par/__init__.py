"""A collection of utilities for mapping a hyper-graph (vertices and nets) to a
SpiNNaker machine.

The task is split into three steps:

* `place`: Assign each vertex to a specific chip.
* `allocate`: Allocate chip resources to each vertex (e.g. cores, memory).
* `route`: Generate routing trees to connect vertices according to their nets.

It is worth emphasising that vertices are generic blobs of resources which are
placed onto a single chip. A vertex will be mapped to exactly one chip however
a chip may be assigned many vertices. The resources consumed by a vertex are
completely user-defined, there is no hard-coded notion of (e.g.) a core or
SDRAM.

General Usage
-------------

Place
`````

Placers have the function prototype::

    place(vertices_resources, nets, machine, constraints, **kwargs)
        -> placement

Where:

* `vertices_resources` is a dictionary `{vertex: resources, ...}` which
  enumerates the resources required by every vertex to be placed. `vertex`
  should be a unique object which sensibly implement `__hash__` and `__eq__`.
  `resources` should be a dictionary `{resource: value, ...}` where `resource`
  is some resource identifier (:py:class:`~.rig.par.resources` defines some
  example resource types though users are free to define their own) and `value`
  is some non-negative integer value.
* `nets` should be a list of :py:class:`~.rig.netlist.Net` objects which refer
  to vertices given in `vertices_resources`.
* `machine` should be a :py:class:`~rig.par.Machine` describing the machine for
  which placement should be carried out.
* `constraints` should be a list of constraints from
  :py:class:`~rig.par.constraints` referring only to vertices in
  `vertices_resources`. Individual placers may define their own additional
  constraints.
* `**kwargs` may be any additional (and optional) implementation-specific
  arguments.

The resulting `placement` is a dictionary `{vertex: position, ...}` which for
each vertex in `vertices_resources` gives a `position` as a tuple `(x, y)`
defining the chip coordinate allocated.

Allocate
````````

Allocators have the function prototype::

    allocate(vertices_resources, nets, machine, constraints, placements,
             **kwargs)
        -> allocation

Where:

* `vertices_resources` as defined above.
* `nets` as defined above.
* `machine` as defined above.
* `constraints` as defined above.
* `placement` is a dictionary of the format returned by a placer.
* `**kwargs` may be any additional (and optional) implementation-specific
  arguments.

The resulting `allocation` is a dictionary `{vertex: {resource: slice, ...},
...}` which for each vertex in `vertices_resources` gives a dictionary of
resource allocations. For each resource consumed by the vertex, the allocation
maps the `resource` identifier to a `:py:class:slice` object which defines the
range over the placed chip's resources allocated to this vertex.

Route
`````

Routers have the function prototype::

    route(vertices_resources, nets, machine, constraints, placements,
          allocation, **kwargs)
        -> routes

Where:

* `vertices_resources` as defined above.
* `nets` as defined above.
* `machine` as defined above.
* `constraints` as defined above.
* `placement` is a dictionary of the format returned by a placer.
* `allocation` is a dictionary of the format returned by an allocator.
* `**kwargs` may be any additional (and optional) implementation-specific
  arguments.

The resulting `routes` is a TODO.


A Note About Resources and Cores
--------------------------------

Resources are completely user-defined quantities however most applications will
use (possibly a subset of) those defined in the `resources` submodule. As you
will see, `Cores` are thus just a standard per-chip resource and have
absolutely no special meaning. As a result, just as a vertex may consume more
than one byte of memory, it may also consume zero, one or more cores. However,
since a vertex is assigned to exactly one chip, it cannot consume more cores
than are available on a single chip: vertices are never be split across chips.
If an application requires this type of behaviour, users must perform this step
in an application-defined preprocessing step before placement.

Users should be careful when using a number of cores greater than one that they
*really* intend to specify that a vertex must be placed on multiple cores of a
single chip. A possible use-case would be a set of application cores which
share local memory.

Likewise, vertices consuming no cores should also be treated carefully. A
possible use-case would be vertices representing external devices where routes
must be set up to and from a device connected to a link in the system. Such
vertices would then typically be subject to constraints to ensure a routes
terminate at a specific link in the system.


Algorithms
----------

Sensible default algorithms have been chosen and are exposed by the names
`place`, `allocate` and `route` in the top level of this module. The general
place and route problem is NP-hard and so this module contains a library of
alternative algorithms for each step in submodules named `place`, `allocate`
and `route` which advanced users are encouraged to peruse to find the most
appropriate algorithm for their task.
"""

from .resources import Cores, SDRAM, SRAM
from .links import Links

from .machine import Machine

# Default algorithms
from .place.hilbert import place
from .allocate.simple import allocate
