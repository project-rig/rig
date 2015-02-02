"""Definitions of constraints for placement and routing.

All constraints defined in this module should be respected by any placement and
routing algorithm. Individual algorithms are permitted to define their own
implementation-specific constraints seperately.
"""


class LocationConstraint(object):
    """Unconditionally place a vertex on a specific chip.

    Attributes
    ----------
    vertex : object
        The user-supplied object representing the vertex.
    location : (x, y)
        The x- and y-coordinates of the chip the vertex must be placed on.
    """

    __slots__ = ["vertex", "location"]

    def __init__(self, vertex, location):
        self.vertex = vertex
        self.location = tuple(location)


class RouteToLinkConstraint(object):
    """Route connected nets to/from a specified link.

    This constraint forces routes to/from the constrained vertex to
    be routed to/from the chip the vertex is placed on and then to/from the
    link specified in the constraint.

    Example Usage
    -------------
    If a silicon retina is attached to the north link of chip (1,1) in a 2x2
    SpiNNaker machine, the following pair of constraints will ensure traffic
    destined for the device vertex is routed to the appropriate link::

        my_device_vertex = ...
        constraints = [LocationConstraint(my_device_vertex, (1, 1)),
                       RouteToLinkConstraint(my_device_vertex, Link.north)]

    Attributes
    ----------
    vertex : object
        The user-supplied object representing the vertex.
    link : :py:class:`~rig.par.Link`
        The link to which routes will be directed.
    """

    __slots__ = ["vertex", "link"]

    def __init__(self, vertex, link):
        self.vertex = vertex
        self.link = link
