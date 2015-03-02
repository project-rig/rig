import pytest

from ..regions import get_region_for_chip, get_minimal_flood_fills


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
    assert get_minimal_flood_fills(targets) == fills
