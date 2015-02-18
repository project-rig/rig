"""Utilities for generating routing tables for SpiNNaker.
"""

from enum import IntEnum

from collections import namedtuple, defaultdict, deque

from six import iteritems

from .machine import Cores, Links


class Routes(IntEnum):
    """Enumeration of routes which a SpiNNaker packet can take after arriving
    at a router.

    Note that the integer values assigned are chosen to match the numbers used
    to identify routes in the low-level software API and hardware registers.

    Note that you can directly cast from a :py:class:`rig.machine.Links` to a
    Routes value.
    """

    @classmethod
    def core(cls, num):
        """Get the identifier for the numbered core."""
        assert 0 <= num <= 17, "Cores are numbered from 0 to 17"
        return cls(6 + num)

    east = 0
    north_east = 1
    north = 2
    west = 3
    south_west = 4
    south = 5

    core_monitor = 6
    core_1 = 7
    core_2 = 8
    core_3 = 9
    core_4 = 10
    core_5 = 11
    core_6 = 12
    core_7 = 13
    core_8 = 14
    core_9 = 15
    core_10 = 16
    core_11 = 17
    core_12 = 18
    core_13 = 19
    core_14 = 20
    core_15 = 21
    core_16 = 22
    core_17 = 23


RoutingTableEntry = namedtuple("RoutingTableEntry", "route key mask")
RoutingTableEntry.__doc__ = """\
Represents a single routing entry in a SpiNNaker routing table.

Entries
-------
route : set([Routes, ...])
    The set of destinations a packet should be routed to where each element
    in the set is a value from the enumeration
    :py:class:`~rig.routing_table.Routes`.
key : int
    32-bit unsigned integer routing key to match after applying the mask.
mask : int
    32-bit unsigned integer mask to apply to keys of packets arriving at the
    router.
"""


class RoutingTree(object):
    """Explicitly defines a multicast route through a SpiNNaker machine.

    Each instance represents a single hop in a route and recursively refers to
    following steps.

    Attributes
    ----------
    chip : (x, y)
        The chip the route is currently passing through.
    children : set
        A set of the next steps in the route. This may be one of:
        * :py:class:`~.rig.routing_table.RoutingTree` representing a step onto
          the next chip
        * :py:class:`~.rig.routing_table.Routes` representing a core or link to
          terminate on.
    """

    __slots__ = ["chip", "children"]

    def __init__(self, chip, children=None):
        self.chip = chip
        self.children = children if children is not None else set()

    def __iter__(self):
        """Iterate over this node and all its children, recursively and in no
        specific order.
        """
        yield self

        for child in self.children:
            if isinstance(child, RoutingTree):
                for subchild in child:
                    yield subchild
            else:
                yield child

    def __repr__(self):
        return "<RoutingTree at {} with {} {}>".format(
            self.chip,
            len(self.children),
            "child" if len(self.children) == 1 else "children")


def build_routing_tables(routes, net_keys):
    """Convert a set of RoutingTrees into a per-chip set of routing tables.

    This command produces routing tables with entries ommitted when the route
    does not change direction.

    Note: The routing trees provided are assumed to be correct and continuous
    (not missing any hops). If this is not the case, the output is undefined.

    Argument
    --------
    routes : {net: :py:class:`~rig.routing_table.RoutingTree`, ...}
        The complete set of RoutingTrees representing all routes in the system.
        (Note: this is the same datastructure produced by routers in the `par`
        module.)
    net_keys : {net: (key, mask), ...}
        The key and mask associated with each net.

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
            if set([direction]) != out_directions:
                routing_tables[(x, y)].append(
                    RoutingTableEntry(out_directions, key, mask))

    return routing_tables
