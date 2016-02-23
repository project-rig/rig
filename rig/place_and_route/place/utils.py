"""Common utility functions for placement algorithms."""

from six import iteritems, itervalues

from rig.netlist import Net

from rig.place_and_route.constraints import \
    LocationConstraint, SameChipConstraint, RouteEndpointConstraint

from rig.place_and_route.exceptions import InsufficientResourceError


def add_resources(res_a, res_b):
    """Return the resources after adding res_b's resources to res_a.

    Parameters
    ----------
    res_a : dict
        Dictionary `{resource: value, ...}`.
    res_b : dict
        Dictionary `{resource: value, ...}`. Must be a (non-strict) subset of
        res_a. If A resource is not present in res_b, the value is presumed to
        be 0.
    """
    return {resource: value + res_b.get(resource, 0)
            for resource, value in iteritems(res_a)}


def subtract_resources(res_a, res_b):
    """Return the resources remaining after subtracting res_b's resources from
    res_a.

    Parameters
    ----------
    res_a : dict
        Dictionary `{resource: value, ...}`.
    res_b : dict
        Dictionary `{resource: value, ...}`. Must be a (non-strict) subset of
        res_a. If A resource is not present in res_b, the value is presumed to
        be 0.
    """
    return {resource: value - res_b.get(resource, 0)
            for resource, value in iteritems(res_a)}


def overallocated(res):
    """Returns true if any resource has a negative value.
    """
    return any(v < 0 for v in itervalues(res))


def resources_after_reservation(res, constraint):
    """Return the resources available after a specified
    ReserveResourceConstraint has been applied.

    Note: the caller is responsible for testing that the constraint is
    applicable to the core whose resources are being constrained.

    Note: this function does not pay attention to the specific position of the
    reserved regieon, only its magnitude.
    """
    res = res.copy()
    res[constraint.resource] -= (constraint.reservation.stop -
                                 constraint.reservation.start)
    return res


def apply_reserve_resource_constraint(machine, constraint):
    """Apply the changes implied by a reserve resource constraint to a
    machine model."""
    if constraint.location is None:
        # Compensate for globally reserved resources
        machine.chip_resources \
            = resources_after_reservation(
                machine.chip_resources, constraint)
        if overallocated(machine.chip_resources):
            raise InsufficientResourceError(
                "Cannot meet {}".format(constraint))
        for location in machine.chip_resource_exceptions:
            machine.chip_resource_exceptions[location] \
                = resources_after_reservation(
                    machine.chip_resource_exceptions[location],
                    constraint)
            if overallocated(machine[location]):
                raise InsufficientResourceError(
                    "Cannot meet {}".format(constraint))
    else:
        # Compensate for reserved resources at a specified location
        machine[constraint.location] = resources_after_reservation(
            machine[constraint.location], constraint)
        if overallocated(machine[constraint.location]):
            raise InsufficientResourceError(
                "Cannot meet {}".format(constraint))


class MergedVertex(object):
    """A group of vertices which have been merged together for use inside a
    placement algorithm."""

    def __init__(self, vertices):
        self.vertices = list(vertices)

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, repr(self.vertices))


def apply_same_chip_constraints(vertices_resources, nets, constraints):
    """Modify a set of vertices_resources, nets and constraints to account for
    all SameChipConstraints.

    To allow placement algorithms to handle SameChipConstraints without any
    special cases, Vertices identified in a SameChipConstraint are merged into
    a new vertex whose vertices_resources are the sum total of their parts
    which may be placed as if a single vertex. Once placed, the placement can
    be expanded into a full placement of all the original vertices using
    :py:func:`finalise_same_chip_constraints`.

    A typical use pattern might look like::

        def my_placer(vertices_resources, nets, machine, constraints):
            # Should be done first thing since this may redefine
            # vertices_resources, nets and constraints.
            vertices_resources, nets, constraints, substitutions = \\
                apply_same_chip_constraints(vertices_resources,
                                            nets, constraints)

            # ...deal with other types of constraint...

            # ...perform placement...

            finalise_same_chip_constraints(substitutions, placements)
            return placements

    Note that this function does not modify its arguments but rather returns
    new copies of the structures supplied.

    Parameters
    ----------
    vertices_resources : {vertex: {resource: quantity, ...}, ...}
    nets : [:py:class:`~rig.netlist.Net`, ...]
    constraints : [constraint, ...]

    Returns
    -------
    (vertices_resources, nets, constraints, substitutions)
        The vertices_resources, nets and constraints values contain modified
        copies of the supplied data structures modified to contain a single
        vertex in place of the individual constrained vertices.

        substitutions is a list of :py:class:`MergedVertex` objects which
        resulted from the combining of the constrained vertices. The order of
        the list is the order the substitutions were carried out. The
        :py:func:`finalise_same_chip_constraints` function can be used to
        expand a set of substitutions.
    """
    # Make a copy of the basic structures to be modified by this function
    vertices_resources = vertices_resources.copy()
    nets = nets[:]
    constraints = constraints[:]

    substitutions = []

    for same_chip_constraint in constraints:
        if not isinstance(same_chip_constraint, SameChipConstraint):
            continue

        # Skip constraints which don't actually merge anything...
        if len(same_chip_constraint.vertices) <= 1:
            continue

        # The new (merged) vertex with which to replace the constrained
        # vertices
        merged_vertex = MergedVertex(same_chip_constraint.vertices)
        substitutions.append(merged_vertex)

        # A set containing the set of vertices to be merged (to remove
        # duplicates)
        merged_vertices = set(same_chip_constraint.vertices)

        # Remove the merged vertices from the set of vertices resources and
        # accumulate the total resources consumed. Note add_resources is not
        # used since we don't know if the resources consumed by each vertex are
        # overlapping.
        total_resources = {}
        for vertex in merged_vertices:
            resources = vertices_resources.pop(vertex)
            for resource, value in iteritems(resources):
                total_resources[resource] = (total_resources.get(resource, 0) +
                                             value)
        vertices_resources[merged_vertex] = total_resources

        # Update any nets which pointed to a merged vertex
        for net_num, net in enumerate(nets):
            net_changed = False

            # Change net sources
            if net.source in merged_vertices:
                net_changed = True
                net = Net(merged_vertex, net.sinks, net.weight)

            # Change net sinks
            for sink_num, sink in enumerate(net.sinks):
                if sink in merged_vertices:
                    if not net_changed:
                        net = Net(net.source, net.sinks, net.weight)
                    net_changed = True
                    net.sinks[sink_num] = merged_vertex

            if net_changed:
                nets[net_num] = net

        # Update any constraints which refer to a merged vertex
        for constraint_num, constraint in enumerate(constraints):
            if isinstance(constraint, LocationConstraint):
                if constraint.vertex in merged_vertices:
                    constraints[constraint_num] = LocationConstraint(
                        merged_vertex, constraint.location)
            elif isinstance(constraint, SameChipConstraint):
                if not set(constraint.vertices).isdisjoint(merged_vertices):
                    constraints[constraint_num] = SameChipConstraint([
                        merged_vertex if v in merged_vertices else v
                        for v in constraint.vertices
                    ])
            elif isinstance(constraint, RouteEndpointConstraint):
                if constraint.vertex in merged_vertices:
                    constraints[constraint_num] = RouteEndpointConstraint(
                        merged_vertex, constraint.route)

    return (vertices_resources, nets, constraints, substitutions)


def finalise_same_chip_constraints(substitutions, placements):
    """Given a set of placements containing the supplied
    :py:class:`MergedVertex`, remove the merged vertices replacing them with
    their constituent vertices (changing the placements inplace).
    """
    for merged_vertex in reversed(substitutions):
        placement = placements.pop(merged_vertex)
        for v in merged_vertex.vertices:
            placements[v] = placement
