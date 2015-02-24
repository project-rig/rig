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
            elif dimension == 2:
                x -= sign
                y -= sign

            # Wrap-around if required
            if width is not None:
                x %= width
            if height is not None:
                y %= height

            yield (x, y)


def to_xyz(xy):
    """Convert a two-tuple (x, y) coordinate into an (x, y, 0) coordinate."""
    x, y = xy
    return (x, y, 0)


def minimise_xyz(xyz):
    """Minimise an (x, y, z) coordinate."""
    x, y, z = xyz
    m = max(min(x, y), min(max(x, y), z))
    return (x-m, y-m, z-m)


def shortest_mesh_path_length(source, destination):
    """Get the length of a shortest path from source to destination without
    using wrap-around links.

    Parameters
    ----------
    source : (x, y, z)
    destination : (x, y, z)

    Returns
    -------
    int
    """
    x, y, z = (d - s for s, d in zip(source, destination))
    # When vectors are minimised, (1,1,1) is added or subtracted from them.
    # This process does not change the range of numbers in the vector. When a
    # vector is minimal, it is easy to see that the range of numbers gives the
    # magnitude since there are at most two non-zero numbers (with opposite
    # signs) and the sum of their magnitudes will also be their range.
    return max(x, y, z) - min(x, y, z)


def shortest_mesh_path(source, destination):
    """Calculate the shortest vector from source to destination without using
    wrap-around links.

    Parameters
    ----------
    source : (x, y, z)
    destination : (x, y, z)

    Returns
    -------
    (x, y, z)
    """
    return minimise_xyz(d - s for s, d in zip(source, destination))


def shortest_torus_path_length(source, destination, width, height):
    """Get the length of a shortest path from source to destination using
    wrap-around links.

    See http://jhnet.co.uk/articles/torus_paths for an explanation of how this
    method works.

    Parameters
    ----------
    source : (x, y, z)
    destination : (x, y, z)
    width : int
    height : int

    Returns
    -------
    int
    """
    # Aliases for convenience
    w, h = width, height

    # Get (non-wrapping) x, y vector from source to destination as if the
    # source was at (0, 0).
    x, y, z = (d - s for s, d in zip(source, destination))
    x, y = x - z, y - z
    x %= w
    y %= h

    return min(max(x, y),          # No wrap
               w - x + y,          # Wrap X only
               x + h - y,          # Wrap Y only
               max(w - x, h - y))  # Wrap X and Y


def shortest_torus_path(source, destination, width, height):
    """Calculate the shortest vector from source to destination using
    wrap-around links.

    See http://jhnet.co.uk/articles/torus_paths for an explanation of how this
    method works.

    Note that when multiple shortest paths exist, one will be chosen at random
    with uniform probability.

    Parameters
    ----------
    source : (x, y, z)
    destination : (x, y, z)
    width : int
    height : int

    Returns
    -------
    (x, y, z)
    """
    # Aliases for convenience
    w, h = width, height

    # Convert to (x,y,0) form
    sx, sy, sz = source
    sx, sy = sx - sz, sy - sz

    # Translate destination as if source was at (0,0,0) and convert to (x,y,0)
    # form where both x and y are not -ve.
    dx, dy, dz = destination
    dx, dy = (dx - dz - sx) % w, (dy - dz - sy) % h

    # The four possible vectors: [(distance, vector), ...]
    approaches = [(max(dx, dy), (dx, dy, 0)),                # No wrap
                  (w-dx+dy, (-(w-dx), dy, 0)),               # Wrap X only
                  (dx+h-dy, (dx, -(h-dy), 0)),               # Wrap Y only
                  (max(w-dx, h-dy), (-(w-dx), -(h-dy), 0))]  # Wrap X and Y

    # Select a minimal approach at random
    _, vector = min(approaches, key=(lambda a: a[0]+random.random()))
    x, y, z = minimise_xyz(vector)

    # Transform to include a random number of 'spirals' on Z axis where
    # possible.
    if abs(x) >= height:
        max_spirals = x // height
        d = random.randint(min(0, max_spirals), max(0, max_spirals)) * height
        x -= d
        z -= d
    elif abs(y) >= width:
        max_spirals = y // width
        d = random.randint(min(0, max_spirals), max(0, max_spirals)) * width
        y -= d
        z -= d

    return (x, y, z)


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
               if (ax + dx) % machine.width == bx
               and (ay + dy) % machine.height == by
               and (ax, ay, link) in machine)
