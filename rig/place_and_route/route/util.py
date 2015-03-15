"""Utility functions which may be of value to router implementations.
"""

import random

from ...machine import Links


def longest_dimension_first(vector, start=(0, 0), width=None, height=None):
    """Generate the (x, y) steps on a longest-dimension first route.

    Note that when multiple dimensions are the same magnitude, one will be
    chosen at random with uniform probability.

    Parameters
    ----------
    vector : (x, y, z)
        The vector which the path should cover.
    start : (x, y)
        The coordinates from which the path should start (note this is a 2D
        coordinate).
    width : int or None
        The width of the topology beyond which we wrap around (0 <= x < width).
        If None, no wrapping on the X axis will occur.
    height : int or None
        The height of the topology beyond which we wrap around (0 <= y <
        height).  If None, no wrapping on the Y axis will occur.

    Generates
    ---------
    (x, y)
        Produces (in order) an (x, y) pair for every hop along the longest
        dimension first route. Ties are broken randomly. The first generated
        value is that of the first hop after the starting position, the last
        generated value is the destination position.
    """
    x, y = start

    for dimension, magnitude in sorted(enumerate(vector),
                                       key=(lambda x:
                                            abs(x[1]) + random.random()),
                                       reverse=True):
        if magnitude == 0:
            break

        # Advance in the specified direction
        sign = 1 if magnitude > 0 else -1
        for _ in range(abs(magnitude)):
            if dimension == 0:
                x += sign
            elif dimension == 1:
                y += sign
            elif dimension == 2:  # pragma: no branch
                x -= sign
                y -= sign

            # Wrap-around if required
            if width is not None:
                x %= width
            if height is not None:
                y %= height

            yield (x, y)


def has_wrap_around_links(machine, minimum_working=0.9):
    """Test if a machine has wrap-around connections installed.

    Since the Machine object does not explicitly define whether a machine has
    wrap-around links they must be tested for directly. This test performs a
    "fuzzy" test on the number of wrap-around links which are working to
    determine if wrap-around links are really present.

    Parameters
    ----------
    machine : :py:class:`~rig.machine.Machine`
    minimum_working : 0.0 <= float <= 1.0
        The minimum proportion of all wrap-around links which must be working
        for this function to return True.

    Returns
    -------
    bool
        True if the system has wrap-around links, False if not.
    """
    working = 0
    for x in range(machine.width):
        if (x, 0, Links.south) in machine:
            working += 1
        if (x, machine.height - 1, Links.north) in machine:
            working += 1
        if (x, 0, Links.south_west) in machine:
            working += 1
        if (x, machine.height - 1, Links.north_east) in machine:
            working += 1

    for y in range(machine.height):
        if (0, y, Links.west) in machine:
            working += 1
        if (machine.width - 1, y, Links.east) in machine:
            working += 1

        # Don't re-count links counted when scanning the x-axis
        if y != 0 and (0, y, Links.south_west) in machine:
            working += 1
        if (y != machine.height - 1 and
                (machine.width - 1, y, Links.north_east) in machine):
            working += 1

    total = (4 * machine.width) + (4 * machine.height) - 2

    return (float(working) / float(total)) >= minimum_working


def links_between(a, b, machine):
    """Get the set of working links connecting chips a and b.

    Parameters
    ----------
    a : (x, y)
    b : (x, y)
    machine : :py:class:`~rig.machine.Machine`

    Returns
    -------
    set([:py:class:`~rig.machine.Links`, ...])
    """
    ax, ay = a
    bx, by = b
    return set(link for link, (dx, dy) in [(Links.east, (1, 0)),
                                           (Links.north_east, (1, 1)),
                                           (Links.north, (0, 1)),
                                           (Links.west, (-1, 0)),
                                           (Links.south_west, (-1, -1)),
                                           (Links.south, (0, -1))]
               if (ax + dx) % machine.width == bx and
               (ay + dy) % machine.height == by and
               (ax, ay, link) in machine)
