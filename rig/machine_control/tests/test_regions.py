import pytest

from ..regions import (get_region_for_chip, compress_flood_fill_regions,
                       minimise_regions, RegionTree)


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


@pytest.mark.parametrize(
    "chips, regions",
    [({(i, j) for i in range(4) for j in range(4)}, {0x00020001}),
     ({(i+4, j) for i in range(4) for j in range(4)}, {0x00020002}),
     ({(i, j+4) for i in range(4) for j in range(4)}, {0x00020010}),
     ({(i, j) for i in range(4) for j in range(4)} |
      {(i+4, j) for i in range(4) for j in range(4)}, {0x00020003}),
     ])
def test_reduce_regions(chips, regions):
    """Test hierarchical reduction of regions."""
    assert set(minimise_regions(chips)) == regions


def test_get_regions_and_cores_for_floodfill():
    """This test looks at trying to minimise the number of flood-fills required
    to load an application.  The required chips are in two level-3 regions and
    have different core requirements for each chip.
    """
    targets = {
        # One region (the same cores)
        (0, 0): {1, 2, 4},
        (0, 1): {1, 2, 4},
        # The next region (same block, different cores)
        (1, 0): {2, 3},
        # The next region (different block)
        (4, 0): {1, 2, 4},
    }

    # This is the return data structure format
    fills = {
        (get_region_for_chip(0, 0, 3) | get_region_for_chip(0, 1, 3),
         (1 << 1) | (1 << 2) | (1 << 4)),
        (get_region_for_chip(1, 0, 3), (1 << 2) | (1 << 3)),
        (get_region_for_chip(4, 0, 3), (1 << 1) | (1 << 2) | (1 << 4)),
    }

    # Test
    assert set(compress_flood_fill_regions(targets)) == fills


class TestRegionTree(object):
    def test_add_coordinate_fails(self):
        t = RegionTree(level=3)

        with pytest.raises(ValueError):
            t.add_coordinate(16, 0)

        with pytest.raises(ValueError):
            t.add_coordinate(0, 16)

    def test_add_coordinate_normal(self):
        t = RegionTree()
        t.add_coordinate(8, 0)
        assert (t.subregions[0].subregions[0].subregions[2].locally_selected ==
                {0})

        t.add_coordinate(0, 8)
        assert (t.subregions[0].subregions[0].subregions[8].locally_selected ==
                {0})

        t.add_coordinate(255, 255)
        assert (
            t.subregions[15].subregions[15].subregions[15].locally_selected ==
            {15}
        )

        pr = t.subregions[0].subregions[0]
        pr.add_coordinate(0, 0)
        sr = t.subregions[0].subregions[0].subregions[0]

        # Should return true when all 16 subregions are filled
        for i in range(4):
            for j in range(4):
                assert sr.add_coordinate(i, j) == (i == 3 and j == 3)

        # This should propagate up
        assert pr.add_coordinate(3, 3) is False
        assert pr.locally_selected == {0}

        # We should be able to get a minimised regions out of this tree
        assert set(t.get_regions()) == {
            0x00020001,  # The last cores to be added should have caused this
            # The other chips we added
            get_region_for_chip(255, 255),
            get_region_for_chip(0, 8),
            get_region_for_chip(8, 0),
        }
