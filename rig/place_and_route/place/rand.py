"""A trivial random placer."""

# This is renamed to ensure that all function correctly use the random number
# generator passed into them.
import random as default_random

from rig.place_and_route.constraints import \
    LocationConstraint, ReserveResourceConstraint

from rig.place_and_route.exceptions import \
    InvalidConstraintError, InsufficientResourceError

from rig.place_and_route.place.utils import \
    subtract_resources, overallocated, \
    apply_reserve_resource_constraint


def place(vertices_resources, nets, machine, constraints,
          random=default_random):
    """A random placer.

    This algorithm performs uniform-random placement of vertices (completely
    ignoring connectivty) and thus in the general case is likely to produce
    very poor quality placements. It exists primarily as a baseline comparison
    for placement quality and is probably of little value to most users.

    Parameters
    ----------
    random : :py:class:`random.Random`
        A Python random number generator. Defaults to ``import random`` but can
        be set to your own instance of :py:class:`random.Random` to allow you
        to control the seed and produce deterministic results. For results to
        be deterministic, vertices_resources must be supplied as an
        :py:class:`collections.OrderedDict`.
    """
    # Within the algorithm we modify the resource availability values in the
    # machine to account for the effects of the current placement. As a result,
    # an internal copy of the structure must be made.
    machine = machine.copy()

    # {vertex: (x, y), ...} gives the location of all vertices, updated
    # throughout the function.
    placements = {}

    # Handle constraints
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

    # The set of vertices which have not been constrained.
    movable_vertices = [v for v in vertices_resources
                        if v not in placements]

    locations = set(machine)

    for vertex in movable_vertices:
        # Keep chosing random chips until we find one where the vertex fits.
        while True:
            if len(locations) == 0:
                raise InsufficientResourceError(
                    "Ran out of chips while attempting to place vertex "
                    "{}".format(vertex))
            location = random.sample(locations, 1)[0]

            resources_if_placed = subtract_resources(
                machine[location], vertices_resources[vertex])

            if overallocated(resources_if_placed):
                # The vertex won't fit on this chip, we'll assume it is full
                # and not try it in the future.
                locations.remove(location)
            else:
                # The vertex fits: record the resources consumed and move on to
                # the next vertex.
                placements[vertex] = location
                machine[location] = resources_if_placed
                break

    return placements
