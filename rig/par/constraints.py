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
        self.location = location


class ReserveResourceConstraint(object):
    """Reserve a range of a resource on all or a specific chip.

    For example, this can be used to reserve areas of SDRAM used by the system
    software to prevent allocations occurring there.

    Note: Reserved ranges must *not* be be partly or fully outside the
    available resources for a chip nor may they overlap with one another.
    Violation of these rules will result in undefined behaviour.

    Note: placers are obliged by this constraint to subtract the reserved
    resource from the total available resource but *not* to determine whether
    the remaining resources include sufficient continuous ranges of resource
    for their placement. Users should thus be extremely careful reserving
    resources which are not immediately at the beginning or end of a resource
    range.

    Attributes
    ----------
    resource : object
        A resource identifier for the resource being reserved.
    reservation : :py:class:`slice`
        The range over that resource which must not be used.
    location : (x, y) or None
        The chip to which this reservation applies. If None then the
        reservation applies globally.
    """

    __slots__ = ["resource", "reservation", "location"]

    def __init__(self, resource, reservation, location=None):
        self.resource = resource
        self.reservation = reservation
        self.location = location


class AlignResourceConstraint(object):
    """Force alignment of start-indices of resource ranges.

    For example, this can be used to ensure assignments into SDRAM are word
    aligned.

    Note: placers are not obliged to be aware of or compensate for wastage of a
    resource due to this constraint and so may produce impossible placements
    when in the even of large numbers of individual items using a non-aligned
    width block of resource.

    Attributes
    ----------
    resource : object
        A resource identifier for the resource to align.
    alignment : int
        The number of which all assigned start-indices must be a multiple.
    """

    __slots__ = ["resource", "alignment"]

    def __init__(self, resource, alignment):
        self.resource = resource
        self.alignment = alignment


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
