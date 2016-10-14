"""SpiNNaker machine regions.

Regions are used to specify areas of a SpiNNaker machine for the purposes of
transmitting nearest neighbour packets or for determining which chips should be
included in any flood-fill of data or application loading.

A 32-bit value representing a region uses the top 16 bits (31:16) to represent
the x- and y-coordinates of the region and the level and the lower 16 bits
(15:0) to represent which of the 16 blocks contained within the chunk should be
selected.

A complete introduction and specification of the region system is given in
"Managing Big SpiNNaker Machines" By Steve Temple.
"""
import array
import collections
from six import iteritems


def get_region_for_chip(x, y, level=3):
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

    Returns
    -------
    int
        A 32-bit value representing the co-ordinates of the chunk of SpiNNaker
        chips that should be selected and the blocks within this chunk that are
        selected.  As long as bits (31:16) are the same these values may be
        OR-ed together to increase the number of sub-blocks selected.
    """
    shift = 6 - 2*level

    bit = ((x >> shift) & 3) + 4*((y >> shift) & 3)  # bit in bits 15:0 to set

    mask = 0xffff ^ ((4 << shift) - 1)  # in {0xfffc, 0xfff0, 0xffc0, 0xff00}
    nx = x & mask  # The mask guarantees that bits 1:0 will be cleared
    ny = y & mask  # The mask guarantees that bits 1:0 will be cleared

    #        sig bits x | sig bits y |  2-bit level  | region select bits
    region = (nx << 24) | (ny << 16) | (level << 16) | (1 << bit)
    return region


def compress_flood_fill_regions(targets):
    """Generate a reduced set of flood fill parameters.

    Parameters
    ----------
    targets : {(x, y) : set([c, ...]), ...}
        For each used chip a set of core numbers onto which an application
        should be loaded.  E.g., the output of
        :py:func:`~rig.place_and_route.util.build_application_map` when indexed
        by an application.

    Yields
    ------
    (region, core mask)
        Pair of integers which represent a region of a SpiNNaker machine and a
        core mask of selected cores within that region for use in flood-filling
        an application.  `region` and `core_mask` are both integer
        representations of bit fields that are understood by SCAMP.

        The pairs are yielded in an order suitable for direct use with SCAMP's
        flood-fill core select (FFCS) method of loading.
    """
    t = RegionCoreTree()

    for (x, y), cores in iteritems(targets):
        for p in cores:
            t.add_core(x, y, p)

    return sorted(t.get_regions_and_coremasks())


class RegionCoreTree(object):
    """A tree structure for use in minimising sets of regions.

    A tree is defined which reflects the definition of SpiNNaker regions like
    so: The tree's root node represents a 256x256 grid of SpiNNaker chips. This
    grid is broken up into 64x64 grids which are represented by the (level 1)
    child nodes of the root.  Each of these level 1 nodes' 64x64 grids are
    broken up into 16x16 grids which are represented by their (level 2)
    children. These level 2 nodes have their 16x16 grids broken up into 4x4
    grids represented by their (level 3) children. Level 3 children explicitly
    list which cores of their sixteen chips are part of the region.

    If any of a level 2 node's level 3 children have all of their chips
    selected for a given core, these level 3 nodes can be removed and replaced
    by a level 2 region with the corresponding 4x4 grid selected. If multiple
    children can be replaced with level 2 regions, these can be combined into a
    single level 2 region with the corresponding 4x4 grids selected, resulting
    in a reduction in the number of regions required. The same process can be
    repeated at each level of the hierarchy eventually producing a minimal set
    of regions.

    This data structure is specified by supplying a sequence of (x, y, p)
    coordinates of cores to be represented by a series of regions using
    :py:meth:`.add_core`. This method minimises the tree during insertion and
    an ordered set of regions and core masks can be extracted by
    :py:meth:`.get_regions_and_coremasks` which simply traverses the tree.
    """
    def __init__(self, base_x=0, base_y=0, level=0):
        self.base_x = base_x
        self.base_y = base_y
        self.scale = 4 ** (4 - level)
        self.shift = 6 - 2*level
        self.level = level

        # For each core number (0-17) we maintain a bitfield indicating for
        # which subregions this core should be filled.
        self.locally_selected = array.array('H', (0x0 for _ in range(18)))

        # If this is a coarser region tree then we also maintain a subtree of
        # fixed size.
        if level < 3:
            self.subregions = [None] * 16

    def get_regions_and_coremasks(self):
        """Generate a set of ordered paired region and core mask representations.

        .. note::
            The region and core masks are ordered such that ``(region << 32) |
            core_mask`` is monotonically increasing. Consequently region and
            core masks generated by this method can be used with SCAMP's
            Flood-Fill Core Select (FFSC) method.

        Yields
        ------
        (region, core mask)
            Pair of integers which represent a region of a SpiNNaker machine
            and a core mask of selected cores within that region.
        """
        region_code = ((self.base_x << 24) | (self.base_y << 16) |
                       (self.level << 16))

        # Generate core masks for any regions which are selected at this level
        # Create a mapping from subregion mask to core numbers
        subregions_cores = collections.defaultdict(lambda: 0x0)
        for core, subregions in enumerate(self.locally_selected):
            if subregions:  # If any subregions are selected on this level
                subregions_cores[subregions] |= 1 << core

        # Order the locally selected items and then yield them
        for (subregions, coremask) in sorted(subregions_cores.items()):
            yield (region_code | subregions), coremask

        if self.level < 3:
            # Iterate through the subregions and recurse, we iterate through in
            # the order which ensures that anything we yield is in increasing
            # order.
            for i in (4*x + y for y in range(4) for x in range(4)):
                subregion = self.subregions[i]
                if subregion is not None:
                    for (region, coremask) in \
                            subregion.get_regions_and_coremasks():
                        yield (region, coremask)

    def add_core(self, x, y, p):
        """Add a new core to the region tree.

        Raises
        ------
        ValueError
            If the co-ordinate is not contained within this part of the tree or
            the core number is out of range.

        Returns
        -------
        bool
            True if the specified core is to be loaded to all subregions.
        """
        # Check that the co-ordinate is contained in this region
        if ((p < 0 or p > 17) or
                (x < self.base_x or x >= self.base_x + self.scale) or
                (y < self.base_y or y >= self.base_y + self.scale)):
            raise ValueError((x, y, p))

        # Determine which subregion this refers to
        subregion = ((x >> self.shift) & 0x3) + 4*((y >> self.shift) & 0x3)

        if self.level == 3:
            # If level-3 then we just add to the locally selected regions
            self.locally_selected[p] |= 1 << subregion
        elif not self.locally_selected[p] & (1 << subregion):
            # If the subregion isn't in `locally_selected` for this core number
            # then add the core to the subregion.
            if self.subregions[subregion] is None:
                # "Lazy": if the subtree doesn't exist yet then add it
                base_x = int(self.base_x + (self.scale / 4) * (subregion % 4))
                base_y = int(self.base_y + (self.scale / 4) * (subregion // 4))
                self.subregions[subregion] = RegionCoreTree(base_x, base_y,
                                                            self.level + 1)

            # If the subregion reports that all of its subregions for this core
            # are selected then we need to add it to `locally_selected`.
            if self.subregions[subregion].add_core(x, y, p):
                self.locally_selected[p] |= 1 << subregion

        # If all subregions are selected for this core and this is not the top
        # level in the hierarchy then return True after emptying the local
        # selection for the core.
        if self.locally_selected[p] == 0xffff and self.level != 0:
            self.locally_selected[p] = 0x0
            return True
        else:
            return False
