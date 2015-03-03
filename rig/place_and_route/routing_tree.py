"""An explicit representation of a routing tree in a machine.

This representation of a route explicitly describes a tree-structure and the
complete path taken by a route. This is used during place and route in
preference to a set of RoutingTableEntry tuples since it is more easily
verified and more accurately represents the problem at hand.
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
        A :py:class:`set` of the next steps in the route. This may be one of:

        * :py:class:`~.rig.place_and_route.routing_tree.RoutingTree`
          representing a step onto the next chip
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
