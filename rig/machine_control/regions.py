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
import collections
from six import iteritems


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


def get_minimal_flood_fills(targets):
    """Return a reduced set of flood fill parameters.

    Parameters
    ----------
    targets : {(x, y) : set([c, ...]), ...}
        For each used chip a set of core numbers onto which an application
        should be loaded.  E.g., the output of
        :py:func:`~rig.place_and_route.util.build_application_map` when indexed
        by an application.

    Returns
    -------
    :py:func:`set` {(region, core_mask), ...}
        Set of region and core mask pairs indicating parameters to use to
        flood-fill an application.  `region` and `core_mask` are both integer
        representations of bit fields that are understood by SCAMP.
    """
    # For each 4x4 block of chips we determine on which chips we would be
    # filling the application to equivalent sets of cores and where this is the
    # case we generate a new region code which contains the two chips.
    # Build a dictionary of the form:
    # {region(31:16): {cores: region(15:0)}, ...}
    # such that adding a new set of cores may allow the merging of region bits
    # (15:0) (indicating specific chips).
    # ----
    # NOTE This is not optimal, but should suffice for the majority of cases.
    # TODO Minimise other cases as well.
    # ----
    region_fills = collections.defaultdict(
        lambda: collections.defaultdict(lambda: 0x0000))

    # For each ((x, y), cores) get the region for the chip and add to the
    # dictionary.
    for ((x, y), cores) in iteritems(targets):
        # Build the core mask
        core_mask = 0x00000000
        for core in cores:
            core_mask |= 1 << core

        # Get the level-3 region: bits (31:16) indicate the 4x4 block of chips,
        # bits (15:0) indicate which of those 16 chips are selected.
        region = get_region_for_chip(x, y, 3)

        # Build the region dict, chips containing equivalent sets of cores in a
        # given level-3 region get placed into the same flood-fill region by
        # OR-ing bits (15:0) of the region code.
        #           [ x and y of region ][  cores  ] |= specific chip in region
        region_fills[region & 0xffff0000][core_mask] |= region & 0x0000ffff

    # Repack the region data into {(region, cores), ...} form, by combining
    # bits (31:16) and (15:0) of the region data and including the core mask.
    fills = set()
    for (regionmsbs, cores) in iteritems(region_fills):
        for (core_mask, regionlsbs) in iteritems(cores):
            #           region with many chips, selected cores in chips
            fills.add((regionmsbs | regionlsbs, core_mask))

    return fills
