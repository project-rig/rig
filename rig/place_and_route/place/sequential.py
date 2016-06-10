"""A flexible greedy sequential placement algorithm."""

from itertools import cycle

from six import next

from rig.place_and_route.constraints import \
    LocationConstraint, ReserveResourceConstraint

from rig.place_and_route.exceptions import \
    InvalidConstraintError, InsufficientResourceError

from rig.place_and_route.place.utils import \
    subtract_resources, overallocated, \
    apply_reserve_resource_constraint, apply_same_chip_constraints, \
    finalise_same_chip_constraints


def place(vertices_resources, nets, machine, constraints,
          vertex_order=None, chip_order=None):
    """Blindly places vertices in sequential order onto chips in the machine.

    This algorithm sequentially places vertices onto chips in the order
    specified (or in an undefined order if not specified). This algorithm is
    essentially the simplest possible valid placement algorithm and is intended
    to form the basis of other simple sequential and greedy placers.

    The algorithm proceeds by attempting to place each vertex on the a chip. If
    the vertex fits we move onto the next vertex (but keep filling the same
    vertex). If the vertex does not fit we move onto the next candidate chip
    until we find somewhere the vertex fits. The algorithm will raise an
    :py:exc:`rig.place_and_route.exceptions.InsufficientResourceError`
    if it has failed to fit a vertex on every chip.

    Parameters
    ----------
    vertex_order : None or iterable
        The order in which the vertices should be attemted to be placed.

        If None (the default), the vertices will be placed in the default
        iteration order of the ``vertices_resources`` argument. If an iterable,
        the iteration sequence should produce each vertex in vertices_resources
        *exactly once*.

    chip_order : None or iterable
        The order in which chips should be tried as a candidate location for a
        vertex.

        If None (the default), the chips will be used in the default iteration
        order of the ``machine`` object (a raster scan). If an iterable, the
        iteration sequence should produce (x, y) pairs giving the coordinates
        of chips to use. All working chip coordinates must be included in the
        iteration sequence *exactly once*. Additional chip coordinates of
        non-existant or dead chips are also allowed (and will simply be
        skipped).
    """
    # If no vertices to place, just stop (from here on we presume that at least
    # one vertex will be placed)
    if len(vertices_resources) == 0:
        return {}

    # Within the algorithm we modify the resource availability values in the
    # machine to account for the effects of the current placement. As a result,
    # an internal copy of the structure must be made.
    machine = machine.copy()

    # {vertex: (x, y), ...} gives the location of all vertices, updated
    # throughout the function.
    placements = {}

    # Handle constraints
    vertices_resources, nets, constraints, substitutions = \
        apply_same_chip_constraints(vertices_resources, nets, constraints)
    for constraint in constraints:
        if isinstance(constraint, LocationConstraint):
            # Location constraints are handled by recording the set of fixed
            # vertex locations and subtracting their resources from the chips
            # they're allocated to.
            location = constraint.location
            if location not in machine:
                raise InvalidConstraintError(
                    "Chip requested by {} unavailable".format(machine))
            vertex = constraint.vertex

            # Record the constrained vertex's location
            placements[vertex] = location

            # Make sure the vertex fits at the requested location (updating the
            # resource availability after placement)
            resources = vertices_resources[vertex]
            machine[location] = subtract_resources(machine[location],
                                                   resources)
            if overallocated(machine[location]):
                raise InsufficientResourceError(
                    "Cannot meet {}".format(constraint))
        elif isinstance(constraint,  # pragma: no branch
                        ReserveResourceConstraint):
            apply_reserve_resource_constraint(machine, constraint)

    if vertex_order is not None:
        # Must modify the vertex_order to substitute the merged vertices
        # inserted by apply_reserve_resource_constraint.
        vertex_order = list(vertex_order)
        for merged_vertex in substitutions:
            # Swap the first merged vertex for its MergedVertex object and
            # remove all other vertices from the merged set
            vertex_order[vertex_order.index(merged_vertex.vertices[0])] \
                = merged_vertex
            # Remove all other vertices in the MergedVertex
            already_removed = set([merged_vertex.vertices[0]])
            for vertex in merged_vertex.vertices[1:]:
                if vertex not in already_removed:
                    vertex_order.remove(vertex)
                    already_removed.add(vertex)

    # The set of vertices which have not been constrained, in iteration order
    movable_vertices = (v for v in (vertices_resources
                                    if vertex_order is None
                                    else vertex_order)
                        if v not in placements)

    # A cyclic iterator over all available chips
    chips = cycle(c for c in (machine if chip_order is None else chip_order)
                  if c in machine)
    chips_iter = iter(chips)

    try:
        cur_chip = next(chips_iter)
    except StopIteration:
        raise InsufficientResourceError("No working chips in machine.")

    # The last chip that we successfully placed something on. Used to detect
    # when we've tried all available chips and not found a suitable candidate
    last_successful_chip = cur_chip

    # Place each vertex in turn
    for vertex in movable_vertices:
        while True:
            resources_if_placed = subtract_resources(
                machine[cur_chip], vertices_resources[vertex])

            if not overallocated(resources_if_placed):
                # The vertex fits: record the resources consumed and move on to
                # the next vertex.
                placements[vertex] = cur_chip
                machine[cur_chip] = resources_if_placed
                last_successful_chip = cur_chip
                break
            else:
                # The vertex won't fit on this chip, move onto the next one
                # available.
                cur_chip = next(chips_iter)

                # If we've looped around all the available chips without
                # managing to place the vertex, give up!
                if cur_chip == last_successful_chip:
                    raise InsufficientResourceError(
                        "Ran out of chips while attempting to place vertex "
                        "{}".format(vertex))

    finalise_same_chip_constraints(substitutions, placements)

    return placements
