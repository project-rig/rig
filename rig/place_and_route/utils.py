"""Utilities functions which assist in the generation of commonly required data
structures from the products of placement, allocation and routing.
"""

from collections import defaultdict, deque

from six import iteritems

from ..machine import Links, Cores

from ..routing_table import Routes, RoutingTableEntry

from .routing_tree import RoutingTree


def build_application_map(vertices_applications, placements, allocations,
                          core_resource=Cores):
    """Build a mapping from application to a list of cores where the
    application is used.

    This utility function assumes that each vertex is associated with a
    specific application.

    Parameters
    ----------
    vertices_applications : {vertex: application, ...}
        Applications are represented by the path of their APLX file.
    placements : {vertex: (x, y), ...}
    allocations : {vertex: {resource: slice, ...}, ...}
        One of these resources should match the `core_resource` argument.
    core_resource : object
        The resource identifier which represents cores.

    Returns
    -------
    {application: {(x, y) : set([c, ...]), ...}, ...}
        For each application, for each used chip a set of core numbers onto
        which the application should be loaded.
    """
    application_map = defaultdict(lambda: defaultdict(set))

    for vertex, application in iteritems(vertices_applications):
        chip_cores = application_map[application][placements[vertex]]
        core_slice = allocations[vertex].get(core_resource, slice(0, 0))
        chip_cores.update(range(core_slice.start, core_slice.stop))

    return application_map


def build_routing_tables(routes, net_keys, omit_default_routes=True):
    """Convert a set of RoutingTrees into a per-chip set of routing tables.

    This command produces routing tables with entries optionally omitted when
    the route does not change direction.

    Note: The routing trees provided are assumed to be correct and continuous
    (not missing any hops). If this is not the case, the output is undefined.

    Parameters
    ----------
    routes : {net: :py:class:`~rig.place_and_route.routing_tree.RoutingTree`, \
              ...}
        The complete set of RoutingTrees representing all routes in the system.
        (Note: this is the same datastructure produced by routers in the `par`
        module.)
    net_keys : {net: (key, mask), ...}
        The key and mask associated with each net.
    omit_default_routes : bool
        Do not create routing entries for routes which do not change direction
        (i.e. use default routing).

    Returns
    -------
    {(x, y): [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
    """
    # {(x, y): [RoutingTableEntry, ...]
    routing_tables = defaultdict(list)

    for net, routing_tree in iteritems(routes):
        key, mask = net_keys[net]

        # A queue of (node, direction) to visit. The direction is the Links
        # entry which describes the direction in which we last moved to reach
        # the current node (or None for the root).
        to_visit = deque([(routing_tree, None)])
        while to_visit:
            node, direction = to_visit.popleft()

            x, y = node.chip

            # Determine the set of directions we must travel to reach the
            # children
            out_directions = set()
            for child in node.children:
                if isinstance(child, RoutingTree):
                    cx, cy = child.chip
                    dx, dy = cx - x, cy - y
                    child_direction = Routes(Links.from_vector((dx, dy)))
                    to_visit.append((child, child_direction))
                    out_directions.add(child_direction)
                else:
                    out_directions.add(child)

            # Add a routing entry when the direction changes
            if not omit_default_routes or set([direction]) != out_directions:
                routing_tables[(x, y)].append(
                    RoutingTableEntry(out_directions, key, mask))

    return routing_tables
