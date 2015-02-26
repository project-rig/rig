Place and Route
===============

Rig provides a set of algorithms and utilities for mapping graph-like
applications onto specific cores in a SpiNNaker machine and defining routes
between them. Broadly, the task is split into three steps:

* **Placement**: Assign graph vertices to a chips.
* **Allocation**: Allocate specific chip resources to each vertex (e.g. cores,
  memory).
* **Routing**: Generate routes to connect vertices according to a supplied set
  of nets.

Rig provides a selection of complementary algorithm implementations for each
step which attempt to carry out these tasks. Users are, of course, free to use
their own application-specific processes in place of any or all of these steps.

Terminology
-----------

The key pieces of terminology used are defined below:

Application Graph
    The `hyper-graph <http://en.wikipedia.org/wiki/Hypergraph>`_ which
    describes how an application's computational resources (the *vertices*) are
    connected to each other by *nets*.
Vertex
    A *vertex* in *application graph*. Each vertex is mapped onto exactly one
    SpiNNaker chip by during the placement process. (Note: an individual
    SpiNNaker chip may have several *vertices* mapped to it). A vertex may
    consume a certain set of *resources*. In most applications a vertex will
    represent an application to be run on a single SpiNNaker core.
    
    *Vertices* are represented by application-defined :py:class:`object`\ s
    which implement :py:meth:`object.__eq__` and :py:meth:`object.__hash__`.
Net
    A (directed) connection from one *vertex* to a number of other *vertices*
    in the *application graph*. During routing, nets are converted into
    specific routes through a SpiNNaker machine which can be used to generate
    routing tables.
    
    *Nets* are represented by instances of the :py:class:`rig.netlist.Net`
    class.
Resource
    A *resource* is any finite resource available to a SpiNNaker chip (e.g.
    SDRAM) which may be consumed by a vertex. *Resources* are allocated to each
    *vertex* during allocation. Users are welcome to define their own
    application-specific resources.
    
    The type of a *resource* is represented by some unique python
    :py:class:`object`. Some common resources are defined in
    :py:mod:`rig.machine` (though users are free to use their own):
    
    * :py:data:`rig.machine.Cores`: Resource identifier for (monitor and
      application) processor cores.
    
    * :py:data:`rig.machine.SDRAM`: Resource identifier for shared off-die
      SDRAM (in bytes).
    
    * :py:data:`rig.machine.SRAM`: Resource identifier for shared on-die SRAM
      (in bytes).
    
    Quantities of a *resource* are represented by positive integer values.
Constraint
    *Constraints* specify additional requirements on how an application graph is
    placed and routed. For example a constraint might be used to force a
    particular *vertex* to always be placed on a specific chip.
    
    A number of types of *constraint* are defined in
    :py:class:`rig.place_and_route.constraints`.

.. note::
    It is worth emphasising that vertices being placed on SpiNNaker *chips*,
    not specific cores. In this library, cores are just one of many chip
    resources which vertices may consume.
    
    For most applications, each vertex represents exactly one core worth of
    work and so each vertex will consume a single core of spinnaker chip
    resource.
    
    Vertices which consume no cores are typically only useful when describing
    external devices connected to the SpiNNaker system.
    
    Vertices which consume more than one core are typically only useful when a
    vertex represents a group of applications which share memory. This is
    because vertices will always be placed on a single SpiNNaker chip: they
    cannot be split accross many chips. If an application requires this type of
    behaviour, users must perform this step in an application-defined process
    prior to placement.

Common case wrapper
-------------------

Most applications simply require their application graph be translated into a
set of data structures describing where binaries need to be loaded and a set of
routing tables. For most users the :py:func:`rig.place_and_route.wrapper`
will do exactly this with a minimum of fuss.

.. autofunction:: rig.place_and_route.wrapper


Placement, allocation and routing algorithms
--------------------------------------------

The three key steps of the place-and-route process (placement, allocation and
routing) are broken into three functions:

* :py:func:`place`
* :py:func:`allocate`
* :py:func:`route`

Since these tasks are largely NP-complete, rig attempts to include a selection
of complimentary algorithms whose function prototypes are shared (and defined
below) to allow users to easily swap between them as required.

Sensible default implementations for each function are aliased as:

* :py:func:`rig.place_and_route.place`
* :py:func:`rig.place_and_route.allocate`
* :py:func:`rig.place_and_route.route`

The details of the available algorithms are described separately:

.. toctree::
    :maxdepth: 2
    
    place_and_route/placement_algorithms
    place_and_route/allocation_algorithms
    place_and_route/routing_algorithms

Function Prototypes
^^^^^^^^^^^^^^^^^^^

The function prototypes shared by all placement, allocation and routing
functions are described below.

.. py:function:: place(vertices_resources, nets, machine, constraints, **kwargs)
    
    Place vertices on specific chips.
    
    The placement must be such that dead chips are not used and chip resources
    are not over-allocated.
    
    Parameters
    ----------
    vertices_resources : {vertex: {resource: quantity, ...}, ...}
        A dictionary from vertex to the required resources for that vertex.
        This dictionary must include an entry for every vertex in the
        application.
        
        Resource requirements are specified by a dictionary `{resource:
        quantity, ...}` where `resource` is some resource identifier and
        `quantity` is a non-negative integer representing the quantity of that
        resource required.
    nets : [:py:class:`~rig.netlist.Net`, ...]
        A list (in no particular order) defining the nets connecting vertices.
    machine : :py:class:`rig.machine.Machine`
        A data structure which defines the resources available in the target
        SpiNNaker machine.
    constraints : [constraint, ...]
        A list of constraints on placement, allocation and routing. Available
        constraints are provided in the
        :py:mod:`rig.place_and_route.constraints` module.
    **kwargs
        Additional implementation-specific options.
    
    Returns
    -------
    {vertex: (x, y), ...}
        A dictionary from vertices to chip coordinate.
    
    Raises
    ------
    rig.place_and_route.exceptions.InvalidConstraintError
        If a constraint is impossible to meet.
    rig.place_and_route.exceptions.InsufficientResourceError
        The placer could not find a placement where sufficient resources are
        available on each core.


.. py:function:: allocate(vertices_resources, nets, machine, constraints, placements, **kwargs)
    
    Allocate chip resources to vertices.
    
    Parameters
    ----------
    vertices_resources : {vertex: {resource: quantity, ...}, ...}
        A dictionary from vertex to the required resources for that vertex.
        This dictionary must include an entry for every vertex in the
        application.
        
        Resource requirements are specified by a dictionary `{resource:
        quantity, ...}` where `resource` is some resource identifier and
        `quantity` is a non-negative integer representing the quantity of that
        resource required.
    nets : [:py:class:`~rig.netlist.Net`, ...]
        A list (in no particular order) defining the nets connecting vertices.
    machine : :py:class:`rig.machine.Machine`
        A data structure which defines the resources available in the target
        SpiNNaker machine.
    constraints : [constraint, ...]
        A list of constraints on placement, allocation and routing. Available
        constraints are provided in the
        :py:mod:`rig.place_and_route.constraints` module.
    placements : {vertex: (x, y), ...}
        A dictionary of the format returned by :py:func:`place` describing a
        set of placements of vertices.
        
        .. warning::
            The placement must not have vertices on dead/non-existent chips.
            failure to comply with this requirement will result in undefined
            behaviour.
    **kwargs
        Additional implementation-specific options.
    
    Returns
    -------
    {vertex: {resource: slice, ...}, ...}
        A dictionary from vertices to the resources allocated to it. Resource
        allocations are dictionaries from resources to a :py:class:`slice`
        defining the range of the given resource type allocated to the vertex.
        These :py:class:`slice` objects have `start` <= `end` and `step` set to
        None (i.e. resources are allocated to vertices in continuous blocks).
    
    Raises
    ------
    rig.place_and_route.exceptions.InvalidConstraintError
        If a constraint is impossible to meet.
    rig.place_and_route.exceptions.InsufficientResourceError
        The allocator could not allocate all desired resources to those
        available.


.. py:function:: route(vertices_resources, nets, machine, constraints, placements, allocations, core_resource=Cores, **kwargs)
    
    Generate routes which connect the vertices defined by a set of nets.
    
    Parameters
    ----------
    vertices_resources : {vertex: {resource: quantity, ...}, ...}
        A dictionary from vertex to the required resources for that vertex.
        This dictionary must include an entry for every vertex in the
        application.
        
        Resource requirements are specified by a dictionary `{resource:
        quantity, ...}` where `resource` is some resource identifier and
        `quantity` is a non-negative integer representing the quantity of that
        resource required.
    nets : [:py:class:`~rig.netlist.Net`, ...]
        A list (in no particular order) defining the nets connecting vertices.
    machine : :py:class:`rig.machine.Machine`
        A data structure which defines the resources available in the target
        SpiNNaker machine.
    constraints : [constraint, ...]
        A list of constraints on placement, allocation and routing. Available
        constraints are provided in the
        :py:mod:`rig.place_and_route.constraints` module.
    placements : {vertex: (x, y), ...}
        A dictionary of the format returned by :py:func:`place` describing a
        set of placements of vertices.
        
        .. warning::
            The placement must not have vertices on dead/non-existent chips.
            failure to comply with this requirement will result in undefined
            behaviour.
    allocations : {vertex: {resource: slice, ...}, ...}
        A dictionary of the format returned by :py:func:`allocate` describing
        the allocation of resources to vertices.
    core_resource : resource (Default: :py:data:`~rig.machine.Cores`)
        **Optional.** Identifier of the resource in `allocations` which
        indicates the cores to route to when routing to a vertex.
        
        .. note::
            Vertices which do not consume this resource will result in routes
            which terminate at the chip they're placed on but do not route to
            any cores.
        
        .. note::
            If no cores are allocated to a vertex, the router will still route
            the net to the chip where the vertex is placed, but not to any
            cores.
    **kwargs
        Additional implementation-specific options.
    
    Returns
    -------
    {:py:class:`~rig.netlist.Net`: :py:class:`~.rig.place_and_route.routing_tree.RoutingTree`, ...}
        A dictionary from nets to routing trees which specify an appropriate
        route through a SpiNNaker machine.

    Raises
    ------
    rig.place_and_route.exceptions.InvalidConstraintError
        If a routing constraint is impossible.
    rig.place_and_route.exceptions.MachineHasDisconnectedSubregion
        If any pair of vertices in a net have no path between them (i.e.
        the system is impossible to route).

Constraints (:py:mod:`rig.place_and_route.constraints`)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: rig.place_and_route.constraints
    :members:

:py:class:`~rig.place_and_route.routing_tree.RoutingTree` data structure
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: rig.place_and_route.routing_tree.RoutingTree
    :members:
    :special-members:

Utility functions
-----------------

.. automodule:: rig.place_and_route.util
    :members:

