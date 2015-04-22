"""High-level wrapper around place and route functions.
"""

from ..machine import Cores, SDRAM

from .constraints import ReserveResourceConstraint, AlignResourceConstraint

from .utils import build_application_map, build_routing_tables

from . import place as default_place
from . import allocate as default_allocate
from . import route as default_route


def wrapper(vertices_resources, vertices_applications,
            nets, net_keys,
            machine, constraints=[],
            reserve_monitor=True, align_sdram=True,
            place=default_place, place_kwargs={},
            allocate=default_allocate, allocate_kwargs={},
            route=default_route, route_kwargs={},
            core_resource=Cores, sdram_resource=SDRAM):
    """Wrapper for core place-and-route tasks for the common case.

    At a high level this function essentially takes a set of vertices and nets
    and produces placements, memory allocations, routing tables and application
    loading information.

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
    vertices_applications : {vertex: application, ...}
        A dictionary from vertices to the application binary to load
        onto cores associated with that vertex. Applications are given as a
        string containing the file name of the binary to load.
    nets : [:py:class:`~rig.netlist.Net`, ...]
        A list (in no particular order) defining the nets connecting vertices.
    net_keys : {:py:class:`~rig.netlist.Net`: (key, mask), ...}
        A dictionary from nets to (key, mask) tuples to be used in SpiNNaker
        routing tables for routes implementing this net. The key and mask
        should be given as 32-bit integers.
    machine : :py:class:`rig.machine.Machine`
        A data structure which defines the resources available in the target
        SpiNNaker machine.
    constraints : [constraint, ...]
        A list of constraints on placement, allocation and routing. Available
        constraints are provided in the
        :py:mod:`rig.place_and_route.constraints` module.
    reserve_monitor : bool (Default: True)
        **Optional.** If True, reserve core zero since it will be used as the
        monitor processor using a
        :py:class:`rig.place_and_route.constraints.ReserveResourceConstraint`.
    align_sdram : bool (Default: True)
        **Optional.** If True, SDRAM allocations will be aligned to 4-byte
        addresses.  Specifically, the supplied constraints will be augmented
        with an `AlignResourceConstraint(sdram_resource, 4)`.
    place : function (Default: :py:func:`rig.place_and_route.place`)
        **Optional.** Placement algorithm to use.
    place_kwargs : dict (Default: {})
        **Optional.** Algorithm-specific arguments for the placer.
    allocate : function (Default: :py:func:`rig.place_and_route.allocate`)
        **Optional.** Allocation algorithm to use.
    allocate_kwargs : dict (Default: {})
        **Optional.** Algorithm-specific arguments for the allocator.
    route : function (Default: :py:func:`rig.place_and_route.route`)
        **Optional.** Routing algorithm to use.
    route_kwargs : dict (Default: {})
        **Optional.** Algorithm-specific arguments for the router.
    core_resource : resource (Default: :py:data:`~rig.machine.Cores`)
        **Optional.** The resource identifier used for cores.
    sdram_resource : resource (Default: :py:data:`~rig.machine.SDRAM`)
        **Optional.** The resource identifier used for SDRAM.

    Returns
    -------
    placements : {vertex: (x, y), ...}
        A dictionary from vertices to the chip coordinate produced by
        placement.
    allocations : {vertex: {resource: slice, ...}, ...}
        A dictionary from vertices to the resources allocated to it. Resource
        allocations are dictionaries from resources to a :py:class:`slice`
        defining the range of the given resource type allocated to the vertex.
        These :py:class:`slice` objects have `start` <= `end` and `step` set to
        None.
    application_map : {application: {(x, y): set([core_num, ...]), ...}, ...}
        A dictionary from application to the set of cores it should be loaded
        onto. The set of cores is given as a dictionary from chip to sets of
        core numbers.
    routing_tables : {(x, y): \
                      [:py:class:`~rig.routing_table.RoutingTableEntry`, \
                       ...], ...}
        The generated routing tables. Provided as a dictionary from chip to a
        list of routing table entries.
    """
    constraints = constraints[:]

    # Augment constraints with commonly used constraints
    if reserve_monitor:
        constraints.append(
            ReserveResourceConstraint(core_resource, slice(0, 1)))
    if align_sdram:
        constraints.append(AlignResourceConstraint(sdram_resource, 4))

    # Place/Allocate/Route
    placements = place(vertices_resources, nets, machine, constraints,
                       **place_kwargs)
    allocations = allocate(vertices_resources, nets, machine, constraints,
                           placements, **allocate_kwargs)
    routes = route(vertices_resources, nets, machine, constraints, placements,
                   allocations, core_resource, **route_kwargs)

    # Build data-structures ready to feed to the machine loading functions
    application_map = build_application_map(vertices_applications, placements,
                                            allocations, core_resource)

    # Build data-structures ready to feed to the machine loading functions
    routing_tables = build_routing_tables(routes, net_keys)

    return placements, allocations, application_map, routing_tables
