"""Utilities for generating routing tables for SpiNNaker.
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
        * :py:class:`~.rig.machine.Links` representing a link to terminate on.
        * A user-defined object to indicate a vertex to terminate on.

        Note: Routing trees only know about chips, links and vertices: they do
        not know about cores. Since in most applications, vertices typically
        consume Cores, users should reffer to a vertex's allocation of cores
        from the 'allocation' step of place-and-route to determine what cores
        are involved in the route.
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
