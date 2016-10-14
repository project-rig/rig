import collections
import pytest

from rig.machine_control.regions import (
    get_region_for_chip, compress_flood_fill_regions, RegionCoreTree)


# NOTE: Test vectors taken from C implementation
@pytest.mark.parametrize(
    "x, y, level, region",
    [(0, 0, 0, 0x00000001),
     (0, 0, 1, 0x00010001),
     (0, 0, 2, 0x00020001),
     (0, 0, 3, 0x00030001),
     (64, 72, 0, 0x00000020),
     (64, 72, 1, 0x40410001),
     (64, 72, 2, 0x40420100),
     (64, 72, 3, 0x404b0001),
     (255, 253, 0, 0x00008000),
     (255, 253, 1, 0xc0c18000),
     (255, 253, 2, 0xf0f28000),
     (255, 253, 3, 0xfcff0080),
     (255,  0, 0, 0x00000008),
     (255,  0, 1, 0xc0010008),
     (255,  0, 2, 0xf0020008),
     (255,  0, 3, 0xfc030008),
     ])
def test_get_region_for_chip(x, y, level, region):
    assert get_region_for_chip(x, y, level) == region


def test_get_regions_and_cores_for_floodfill():
    """This test looks at trying to minimise the number of flood-fills required
    to load an application.  The required chips are in two level-3 regions and
    have different core requirements for each chip.
    """
    targets = {
        (0, 0): {1, 2, 4},
        (0, 1): {1, 2, 4},
        (1, 0): {2, 3},
        (4, 0): {1, 2, 4},
    }

    # Test
    seen_fills = collections.defaultdict(set)
    last = (0, 0)
    for (region, cores) in compress_flood_fill_regions(targets):
        assert (region, cores) >= last
        last = (region, cores)

        # Extract the data from the region
        level = (region >> 16) & 0x3
        assert level == 3

        # Base x and y
        nx = (region >> 24) & 0xfc
        ny = (region >> 16) & 0xfc

        for x in range(4):
            for y in range(4):
                # Subregion select bit
                bit = 1 << ((x & 3) | 4*(y & 3))

                if region & bit:
                    seen_fills[(nx + x, ny + y)].update(
                        {i for i in range(18) if cores & (1 << i)})

    assert seen_fills == targets


def test_get_regions_and_cores_for_floodfill_ordering():
    """This test explicitly checks that ordering across subregions works
    correctly. Two level-3 regions are created in the level-2 region
    originating at (0, 0). Importantly these two lower-level regions are
    arranged in increasing order on the x-axis. A further level-3 region is
    then created *in a different level-2 subregion* at x=0 and y=64.
    """
    targets = {
        (0, 0): {1},
        (4, 0): {1},
        (0, 64): {1},
    }

    # Test the ordering across the subregions
    last = (0, 0)
    for (region, cores) in compress_flood_fill_regions(targets):
        assert (region, cores) >= last
        last = (region, cores)


class TestRegionCoreTree(object):
    @pytest.mark.parametrize("x, y, p", [(16, 0, 1), (0, 16, 1), (0, 0, 25)])
    def test_add_core_fails(self, x, y, p):
        t = RegionCoreTree(level=3)

        with pytest.raises(ValueError):
            t.add_core(x, y, p)

    def test_add_core_normal_level_3(self):
        """Test adding cores to a level 3 tree works as expected."""
        t = RegionCoreTree(level=3)

        assert not t.add_core(0, 0, 5)
        assert t.locally_selected[5] == 0b1

        assert not t.add_core(0, 1, 0)
        assert t.locally_selected[0] == 0b10000

        assert not t.add_core(3, 0, 0)
        assert t.locally_selected[0] == 0b11000

        assert not t.add_core(2, 0, 0)
        assert t.locally_selected[0] == 0b11100

        assert not t.add_core(1, 0, 0)
        assert t.locally_selected[0] == 0b11110

        assert not t.add_core(0, 0, 0)
        assert t.locally_selected[0] == 0b11111

        # Add core 7 to all chips and ensure that add_core returns true for the
        # last entry.
        for x in range(4):
            for y in range(4):
                if (x, y) != (3, 3):
                    t.add_core(x, y, 7)

        assert t.locally_selected[7] == 0x7fff

        # Selecting a core in all regions should cause `add_core` to return
        # true and to deselect the all regions for that core.
        assert t.add_core(3, 3, 7) is True
        assert t.locally_selected[7] == 0x0

    def test_add_core_normal_level_2(self):
        """Test adding cores to a level 2 tree works as expected, this is a
        test of the hierarchy.
        """
        t = RegionCoreTree(level=2)

        # Add a core to the first subregion
        assert not t.add_core(0, 0, 0)
        assert t.subregions[0].locally_selected[0] == 0x1

        # Add a core to the other subregions
        i = 0
        for _y in range(4):
            for _x in range(4):
                x = _x * 4
                y = _y * 4

                assert not t.add_core(x, y, 0)
                assert t.subregions[i].locally_selected[0] == 0x1
                i += 1

        # Fill a core in one of the subregions and ensure that it gets selected
        # at the level-2 level.
        for _x in range(4):
            for _y in range(4):
                x = _x + 12
                y = _y + 12

                assert not t.add_core(x, y, 5)

        assert t.locally_selected[5] == 0x8000
        assert t.subregions[15].locally_selected[5] == 0x0

    def test_get_regions_cores_level_3(self):
        """Test for correct computation and ordering of regions and cores when
        extracted from a level 3 region.
        """
        t = RegionCoreTree(level=3)

        # Add cores to the tree
        t.add_core(0, 0, 1)
        t.add_core(3, 3, 1)
        t.add_core(3, 3, 2)
        t.add_core(0, 0, 2)
        t.add_core(3, 0, 0)
        t.add_core(0, 1, 3)

        # Check that all the expected regions and core masks are produced IN
        # THE EXPECTED ORDER.
        # NB: The first three entries above are merged to become the first
        # entry below.
        expected_regions_cores = {
            (get_region_for_chip(3, 3) | get_region_for_chip(0, 0), 0b0110),
            (get_region_for_chip(3, 0), 0b0001),
            (get_region_for_chip(0, 1), 0b1000),
        }
        seen_regions_cores = set([])

        last = 0x0
        for (region, coremask) in t.get_regions_and_coremasks():
            # Check the ordering
            assert (region << 32 | coremask) >= last
            last = (region << 32 | coremask)

            # Add to the entries we've seen
            seen_regions_cores.add((region, coremask))

        assert seen_regions_cores == expected_regions_cores

    def test_get_regions_cores_with_subregions(self):
        """Test for correct computation and ordering of regions and cores when
        extracted from a tree with more depth.
        """
        t = RegionCoreTree()

        # Add cores to the tree
        # Cores 0 and 10 are present on all chips
        for x in range(256):
            for y in range(256):
                t.add_core(x, y, 0)
                t.add_core(x, y, 10)

        # Core 1 is present on all but one level 3 region in the level 2 region
        # beginning at (128, 64)
        for x in range(16):
            for y in range(16):
                if x < 4 and y < 4:
                    continue

                t.add_core(x + 128, y + 64, 1)

        # ORDER TEST
        # Core 4 is present on all chips in the level 3 region beginning at (0,
        # 252); this should come before Core 2 is on (0, 252) [higher level
        # regions before lower level regions]; which should come before Core 3
        # on (252, 0) [obey the region indexing - increasing y before
        # increasing x].
        for x in range(4):
            for y in range(4):
                t.add_core(0+x, 252+y, 4)
        t.add_core(0, 252, 2)
        t.add_core(252, 0, 3)

        # Check that all the expected regions and core masks are produced IN
        # THE EXPECTED ORDER.
        expected_regions_cores = {
            (get_region_for_chip(0, 0, level=0) | 0xffff, 0x1 | (1 << 10)),
            ((get_region_for_chip(128, 64, level=2) & 0xffff0000) | 0xfffe,
             0b0010),
            (get_region_for_chip(0, 252), 0b0100),
            (get_region_for_chip(0, 252, level=2), 0b10000),
            (get_region_for_chip(252, 0), 0b1000),
        }
        seen_regions_cores = set([])

        last = 0x0
        for (region, coremask) in t.get_regions_and_coremasks():
            # Check the ordering
            assert (region << 32 | coremask) >= last
            last = (region << 32 | coremask)

            # Add to the entries we've seen
            seen_regions_cores.add((region, coremask))

        assert seen_regions_cores == expected_regions_cores

    def test_get_regions_cores_with_subregions_no_repeats(self):
        t = RegionCoreTree()

        for x in range(4):
            for y in range(4):
                t.add_core(x, y, 1)

        # This core added after a region merge occurred
        t.add_core(x, y, 1)

        assert len(list(t.get_regions_and_coremasks())) == 1
