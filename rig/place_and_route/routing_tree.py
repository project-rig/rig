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
        A :py:class:`set` of the next steps in the route represented by a
        (route, object) tuple.

        The route must be either :py:class:`~rig.routing_table.Routes` or
        `None`. If :py:class:`~rig.routing_table.Routes` then this indicates
        the next step in the route uses a particular route.

        The object indicates the intended destination of this step in the
        route. It may be one of:

        * :py:class:`~.rig.place_and_route.routing_tree.RoutingTree`
          representing the continuation of the routing tree after following a
          given link. (Only used if the :py:class:`~rig.routing_table.Routes`
          object is a link and not a core).
        * A vertex (i.e. some other Python object) when the route terminates at
          the supplied vertex. Note that the direction may be None and so
          additional logic may be required to determine what core to target to
          reach the vertex.
    """

    def __init__(self, chip, children=None):
        self.chip = chip
        self.children = children if children is not None else set()

    def __iter__(self):
        """Iterate over this node and then all its children, recursively and in
        no specific order. This iterator iterates over the child *objects*
        (i.e. not the route part of the child tuple).
        """
        yield self

        for route, obj in self.children:
            if isinstance(obj, RoutingTree):
                for subchild in obj:
                    yield subchild
            else:
                yield obj

    def __repr__(self):
        return "<RoutingTree at {} with {} {}>".format(
            self.chip,
            len(self.children),
            "child" if len(self.children) == 1 else "children")
