import pytest

from ..regions import get_region_for_chip


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
