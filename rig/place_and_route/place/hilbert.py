"""A minimal and dumb placement algorithm.
"""

from math import log, ceil

from rig.place_and_route.place.sequential import place as sequential_place
from rig.place_and_route.place.breadth_first import breadth_first_vertex_order


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


def hilbert_chip_order(machine):
    """A generator which iterates over a set of chips in a machine in a hilbert
    path.

    For use as a chip ordering for the sequential placer.
    """
    max_dimen = max(machine.width, machine.height)
    hilbert_levels = int(ceil(log(max_dimen, 2.0))) if max_dimen >= 1 else 0
    return hilbert(hilbert_levels)


def place(vertices_resources, nets, machine, constraints, breadth_first=True):
    """Places vertices in breadth-first order along a hilbert-curve path
    through the chips in the machine.

    This is a thin wrapper around the :py:func:`sequential
    <rig.place_and_route.place.sequential.place>` placement algorithm which
    optionally uses the :py:func:`breadth_first_vertex_order` vertex ordering
    (if the breadth_first argument is True, the default) and
    :py:func:`hilbert_chip_order` for chip ordering.

    Parameters
    ----------
    breadth_first : bool
        Should vertices be placed in breadth first order rather than the
        iteration order of vertices_resources. True by default.
    """
    return sequential_place(vertices_resources, nets,
                            machine, constraints,
                            (None if not breadth_first else
                             breadth_first_vertex_order(vertices_resources,
                                                        nets)),
                            hilbert_chip_order(machine))
