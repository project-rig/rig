"""General-purpose SpiNNaker-related geometry functions.
"""

import random

import numpy as np


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


def concentric_hexagons(radius, start=(0, 0)):
    """A generator which produces coordinates of concentric rings of hexagons.

    Parameters
    ----------
    radius : int
        Number of layers to produce (0 is just one hexagon)
    start : (x, y)
        The coordinate of the central hexagon.
    """
    x, y = start
    yield (x, y)
    for r in range(1, radius + 1):
        # Move to the next layer
        y -= 1
        # Walk around the hexagon of this radius
        for dx, dy in [(1, 1), (0, 1), (-1, 0), (-1, -1), (0, -1), (1, 0)]:
            for _ in range(r):
                yield (x, y)
                x += dx
                y += dy


def spinn5_eth_coords(width, height):
    """Generate a list of board coordinates with Ethernet connectivity in a
    SpiNNaker machine.

    Specifically, generates the coordinates for the ethernet connected chips of
    SpiNN-5 boards arranged in a standard torus topology.

    Parameters
    ----------
    width : int
        Width of the system in chips.
    height : int
        Height of the system in chips.
    """
    # Internally, work with the width and height rounded up to the next
    # multiple of 12
    w = ((width + 11) // 12) * 12
    h = ((height + 11) // 12) * 12

    for x in range(0, w, 12):
        for y in range(0, h, 12):
            for dx, dy in ((0, 0), (4, 8), (8, 4)):
                nx = (x + dx) % w
                ny = (y + dy) % h
                # Skip points which are outside the range available
                if nx < width and ny < height:
                    yield (nx, ny)


def spinn5_local_eth_coord(x, y, w, h):
    """Get the coordinates of a chip's local ethernet connected chip.

    .. note::
        This function assumes the system is constructed from SpiNN-5 boards
        returns the coordinates of the ethernet connected chip on the current
        board.

    Parameters
    ----------
    x : int
    y : int
    w : int
        Width of the system in chips.
    h : int
        Height of the system in chips.
    """
    dx, dy = SPINN5_ETH_OFFSET[y % 12][x % 12]
    return ((x + dx) % w), ((y + dy) % h)


SPINN5_ETH_OFFSET = np.array([
    [(vx - x, vy - y) for x, (vx, vy) in enumerate(row)]
    for y, row in enumerate([
        # Below is an enumeration of the absolute coordinates of the nearest
        # ethernet connected chip. Note that the above list comprehension
        # changes these into offsets to the nearest chip.
        # X:   0         1         2         3         4         5         6         7         8         9        10        11     # noqa Y:
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, -4), (+4, -4), (+4, -4), (+4, -4), (+4, -4), (+4, -4), (+4, -4)],  # noqa  0
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, -4), (+4, -4), (+4, -4), (+4, -4), (+4, -4), (+4, -4)],  # noqa  1
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, -4), (+4, -4), (+4, -4), (+4, -4), (+4, -4)],  # noqa  2
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, -4), (+4, -4), (+4, -4), (+4, -4)],  # noqa  3
        [(-4, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  4
        [(-4, +4), (-4, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  5
        [(-4, +4), (-4, +4), (-4, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  6
        [(-4, +4), (-4, +4), (-4, +4), (-4, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  7
        [(-4, +4), (-4, +4), (-4, +4), (-4, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+8, +4), (+8, +4), (+8, +4)],  # noqa  8
        [(-4, +4), (-4, +4), (-4, +4), (-4, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+8, +4), (+8, +4)],  # noqa  9
        [(-4, +4), (-4, +4), (-4, +4), (-4, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+8, +4)],  # noqa 10
        [(-4, +4), (-4, +4), (-4, +4), (-4, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8)]   # noqa 11
    ])
])
"""SpiNN-5 ethernet connected chip lookup.

Used by :py:func:`.spinn5_local_eth_coord`. Given an x and y chip position
modulo 12, return the offset of the board's bottom-left chip from the chip's
position.

Note: the order of indexes: ``SPINN5_ETH_OFFSET[y][x]``!
"""
