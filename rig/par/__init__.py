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

In the common-case, users are referred to :py:class:`~rig.par.par` which is a
wrapper function around the common-case uses of the utilities in this module.
This wrapper is very simple and essentially calls `place`, `allocate` and
`route` in sequence, avoiding a certain amount of boilerplate.

The underlying functions, which users are free to use directly if desired, are
defined as follows.

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
  is some resource identifier (:py:class:`~.rig.machine` defines names for some
  common resource types though users are free to (re)define their own) and
  `value` is some non-negative integer value.
* `nets` should be a list of :py:class:`~.rig.netlist.Net` objects which refer
  to vertices given in `vertices_resources`.
* `machine` should be a :py:class:`~rig.machine.Machine` describing the machine
  for which placement should be carried out.
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
        -> allocations

Where:

* `vertices_resources` as defined above.
* `nets` as defined above.
* `machine` as defined above.
* `constraints` as defined above.
* `placement` is a dictionary of the format returned by a placer. Note that
  this placement must be valid (i.e. no vertices on dead/non-existant chips):
  failiure to comply with this requirement will result in undefined behaviour.
* `**kwargs` may be any additional (and optional) implementation-specific
  arguments.

The resulting `allocation` is a dictionary `{vertex: {resource: slice, ...},
...}` which for each vertex in `vertices_resources` gives a dictionary of
resource allocations. For each resource consumed by the vertex, the allocation
maps the `resource` identifier to a `:py:class:slice` object which defines the
range over the placed chip's resources allocated to this vertex. This slice
will have its `start` and `stop` fields defined while `step` will be `None`
(since range allocations are always continuous).

Route
`````

Routers have the function prototype::

    route(vertices_resources, nets, machine, constraints, placements,
          allocations, core_resource=Cores, **kwargs)
        -> routes

Where:

* `vertices_resources` as defined above.
* `nets` as defined above.
* `machine` as defined above.
* `constraints` as defined above.
* `placements` is a dictionary of the format returned by a placer. Note that
  this placement must be valid (i.e. no vertices on dead/non-existant chips):
  failiure to comply with this requirement will result in undefined behaviour.
* `allocations` is a dictionary as produced by an allocator.
* `core_resource` is the identifier of the resource in `allocations` which
  indicates the cores to route to when routing to a vertex. This defaults to
  :py:class:`~rig.machine.Cores` but may be re-defined at will. Note: If no
  cores are allocated to a vertex, the router will still route the net to the
  chip the vertex is placed on but not to any cores.
* `**kwargs` may be any additional (and optional) implementation-specific
  arguments.

The resulting `routes` is a dictionary mapping from nets to
:py:class:`~.rig.par.routing_tree.RoutingTree` objects defining the routes
which connect the associated net.


A Note About Resources and Cores
--------------------------------

Resources are completely user-defined quantities however most applications will
use (possibly a subset of) those defined in the :py:class:`~rig.machine`
module. As you will see, `Cores` are thus just a standard per-chip resource and
have absolutely no other special meaning. This simplifies implementation of
placement/allocation/routing but has a few subtle side-effects:

* Most users will wish to use a ReserveResourceConstraint to indicate that core
  0 is in use as a monitor processor and cannot be allocated.

* One can allocate zero, one or multiple cores at once, an ability which should
  be treated with some care (see below).

* Routers *do* in fact care about cores and thus, in order to produce a routing
  with routes which terminates in cores, there must exist exactly one resource
  which mapps 1:1 to cores on a chip. Note that if this is not done, routers
  still produce routes which connect all involved chips but these routes simply
  wont terminate with a core.

As a result, just as a vertex may consume more than one byte of memory, it may
also consume zero, one or more cores.  However, since a vertex is assigned to
exactly one chip, it cannot consume more cores than are available on a single
chip: vertices are never be split across chips.  If an application requires
this type of behaviour, users must perform this step in an application-defined
preprocessing step before placement.

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

# Default algorithms
from .place.hilbert import place
from .allocate.greedy import allocate
from .route.ner import route

# High-Level Wrapper
from .wrapper import par
