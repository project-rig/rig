"""A minimal and dumb placement algorithm.
"""

from six import next

from math import log, ceil

from collections import deque

from ..exceptions import InsufficientResourceError, InvalidConstraintError

from ..constraints import LocationConstraint, ReserveResourceConstraint

from .utils import \
    subtract_resources, overallocated, apply_reserve_resource_constraint, \
    apply_same_chip_constraints, finalise_same_chip_constraints


def hilbert(level, angle=1, s=None):
    """Generator of points along a 2D Hilbert curve.

    This implements the L-system as described on
    `http://en.wikipedia.org/wiki/Hilbert_curve`.

    Parameters
    ----------
    level : int
        Number of levels of recursion to use in generating the curve. The
        resulting curve will be `(2**level)-1` wide/tall.
    angle : int
        **For internal use only.** `1` if this is the 'positive' expansion of
        the grammar and `-1` for the 'negative' expansion.
    s : HilbertState
        **For internal use only.** The current state of the system.
    """
    # An internal (mutable) state object (note: used in place of a closure with
    # nonlocal variables for Python 2 support).
    class HilbertState(object):
        def __init__(self, x=0, y=0, dx=1, dy=0):
            self.x, self.y, self.dx, self.dy = x, y, dx, dy

    # Create state object first time we're called while also yielding first
    # position
    if s is None:
        s = HilbertState()
        yield s.x, s.y

    if level <= 0:
        return

    # Turn left
    s.dx, s.dy = s.dy*-angle, s.dx*angle

    # Recurse negative
    for s.x, s.y in hilbert(level - 1, -angle, s):
        yield s.x, s.y

    # Move forward
    s.x, s.y = s.x + s.dx, s.y + s.dy
    yield s.x, s.y

    # Turn right
    s.dx, s.dy = s.dy*angle, s.dx*-angle

    # Recurse positive
    for s.x, s.y in hilbert(level - 1, angle, s):
        yield s.x, s.y

    # Move forward
    s.x, s.y = s.x + s.dx, s.y + s.dy
    yield s.x, s.y

    # Recurse positive
    for s.x, s.y in hilbert(level - 1, angle, s):
        yield s.x, s.y

    # Turn right
    s.dx, s.dy = s.dy*angle, s.dx*-angle

    # Move forward
    s.x, s.y = s.x + s.dx, s.y + s.dy
    yield s.x, s.y

    # Recurse negative
    for s.x, s.y in hilbert(level - 1, -angle, s):
        yield s.x, s.y

    # Turn left
    s.dx, s.dy = s.dy*-angle, s.dx*angle


def place(vertices_resources, nets, machine, constraints):
    """Places vertices greedily and dumbly along a Hilbert-curve through the
    machine.
    """
    placements = {}

    # Working copy of machine which will be updated to account for effects of
    # constraints.
    machine = machine.copy()

    # Handle constraints
    vertices_resources, nets, constraints, substitutions = \
        apply_same_chip_constraints(vertices_resources, nets, constraints)
    unplaced_vertices = set(vertices_resources)
    for constraint in constraints:
        if isinstance(constraint, LocationConstraint):
            # Flag resources consumed for the specified chip
            loc = constraint.location
            if loc not in machine:
                raise InvalidConstraintError(
                    "Chip requested by {} unavailable".format(constraint))
            vertex_resources = vertices_resources[constraint.vertex]
            machine[loc] = subtract_resources(machine[loc], vertex_resources)
            if overallocated(machine[loc]):
                raise InsufficientResourceError(
                    "Cannot meet {}".format(constraint))

            # Place the vertex
            unplaced_vertices.remove(constraint.vertex)
            placements[constraint.vertex] = loc
        elif isinstance(constraint,  # pragma: no branch
                        ReserveResourceConstraint):
            apply_reserve_resource_constraint(machine, constraint)

    # Allocate chips along a Hilbert curve large enough to cover the whole
    # system
    max_dimen = max(machine.width, machine.height)
    hilbert_levels = int(ceil(log(max_dimen, 2.0))) if max_dimen >= 1 else 0
    hilbert_iter = hilbert(hilbert_levels)

    # A coordinates of the current chip and a copy of its resources which will
    # be decremented as vertices are placed. Since we don't allow back-tracking
    # this means there is no need to log resource usage for anything but the
    # current chip.
    cur_chip = None
    cur_chip_resources = None

    # Perform a breadth-first iteration over the vertices (a simple heuristic
    # for placing related nodes in proximal locations).
    vertex_queue = deque()
    while vertex_queue or unplaced_vertices:
        # If out of vertices in the queue, grab an unplaced one arbitrarily
        if not vertex_queue:
            vertex_queue.append(next(iter(unplaced_vertices)))

        vertex = vertex_queue.popleft()
        if vertex not in unplaced_vertices:
            continue

        resources = vertices_resources[vertex]

        # Attempt to find a chip with free resources
        while True:
            try:
                if cur_chip is None:
                    cur_chip = next(hilbert_iter)
                    if cur_chip not in machine:
                        cur_chip = None
                        continue
                    cur_chip_resources = machine[cur_chip].copy()
            except StopIteration:
                raise InsufficientResourceError(
                    "Ran out of chips while "
                    "{} vertices remain unplaced".format(
                        len(unplaced_vertices)))
            cur_chip_resources = subtract_resources(
                cur_chip_resources, resources)
            if not overallocated(cur_chip_resources):
                break
            else:
                cur_chip = None
                continue

        # Affect the placement
        unplaced_vertices.remove(vertex)
        placements[vertex] = cur_chip

        # Continue the iteration breadth-first through the vertices
        for net in nets:
            if vertex in net:
                vertex_queue.append(net.source)
                vertex_queue.extend(net.sinks)

    finalise_same_chip_constraints(substitutions, placements)

    return placements
