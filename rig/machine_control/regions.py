"""SpiNNaker machine regions.

.. todo::
    Neaten this documentation!

Regions (not to be confused with rig Regions) are used to specify areas of a
SpiNNaker machine for the purposes of transmitting nearest neighbour packets or
for determining which chips should be included in any flood-fill of data or
application loading.

Regions are split into 4 levels (0, 1, 2 and 3) referring to increasing
coarseness in the number of chips they are able to represent.  Level 3 splits a
256x256 SpiNNaker machine (the largest possible) into a grid of m nxn chunks,
in each chunk blocks of pxp chips may be selected.  Level 2 splits each nxn
chunk into m oxo chunks, and so on.  By level 0 it is possible to select
individual chips from a 4x4 grid of chips.

A 32-bit value representing a region uses the top 16 bits (31:16) to represent
the x- and y-coordinates of the region and the level and the lower 16 bits
(15:0) to represent which of the 16 blocks contained within the chunk should be
selected.
"""


def get_region_for_chip(x, y, level=0):
    """Get the region word for the given chip co-ordinates.

    Parameters
    ----------
    x : int
        x co-ordinate
    y : int
        y co-ordinate
    level : int
        Level of region to build. 0 is the most coarse and 3 is the finest.
        When 3 is used the specified region will ONLY select the given chip,
        for other regions surrounding chips will also be selected.

    .. warning::
        Translated from a C function which is pretty much the only
        documentation of this system.

    Returns
    -------
    int
        A 32-bit value representing the co-ordinates of the chunk of SpiNNaker
        chips that should be selected and the blocks within this chunk that are
        selected.  As long as bits (31:16) are the same these values may be
        OR-ed together to increase the number of sub-blocks selected.
    """
    # NOTE: For those privileged few with access to SC&MP code - this is a
    # translation of the function `compute_level` in `scamp-nn.c`.
    shift = 6 - 2*level
    mask = ~((4 << shift) - 1)
    bit = ((x >> shift) & 3) + 4*((y >> shift) & 3)  # bit in bits 15:0 to set
    nx = x & mask
    ny = y & mask

    region = (nx << 24) | ((ny + level) << 16) | (1 << bit)
    return region
