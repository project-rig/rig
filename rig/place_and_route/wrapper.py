"""High-level wrapper around place and route functions.
"""

from ..machine import Cores, SDRAM

from .constraints import ReserveResourceConstraint, AlignResourceConstraint

from .util import build_application_map, build_routing_tables

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

    This wrapper aims to be a simple wrapper around the place-and-route process
    which reduces boilerplate code in the common case. At a high level this
    function essentially takes a set of vertices and nets and produces
    placements, memory allocations and routing tables.

    Arguments
    ---------
    vertices_resources : {vertex: {resource: quantity, ...}, ...}
    vertices_applications : {vertex: application}
    nets : [:py:class:`~rig.netlist.Net`, ...]
    net_keys : {:py:class:`~rig.netlist.Net`: (key, mask), ...}
    machine : :py:class:`~rig.machine.Machine`

    Optional Arguments
    ------------------
    constraints : [constraint, ...]
    reserve_monitor : bool
        If True, reserve core zero since it will be used as the monitor
        processor. Specifically, the supplied constraints will be augmented
        with a `ReserveResourceConstraint(core_resource, slice(0, 1))`. This
        has the effect of reserving the zeroth element of the `core_resource`
        resource (see later argument).
    align_sdram : bool
        If True, SDRAM allocations will be aligned to 4-byte addresses.
        Specifically, the supplied constraints will be augmented with an
        `AlignResourceConstraint(sdram_resource, 4)`.
    place : function
        Placement algorithm to use.
    place_kwargs : dict
        Algorithm-specific arguments for the placer.
    allocate : function
        Allocation algorithm to use.
    allocate_kwargs : dict
        Algorithm-specific arguments for the allocator.
    route : function
        Routing algorithm to use.
    route_kwargs : dict
        Algorithm-specific arguments for the router.
    core_resource : resource
        The resource identifier used for cores.
    sdram_resource : resource
        The resource identifier used for SDRAM.

    Returns
    -------
    placements : {vertex: (x, y), ...}
    allocations : {vertex: {resource: slice, ...}, ...}
    application_map : {application: {(x, y): set([core_num, ...]), ...}, ...}
    routing_tables : {(x, y): [RoutingTableEntry, ...], ...}
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
