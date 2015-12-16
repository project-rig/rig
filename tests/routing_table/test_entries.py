import pytest

from rig.links import Links

from rig.routing_table import Routes, RoutingTableEntry


class TestRoutingTableEntry(object):
    def test_str(self):
        # Check that the MSB and LSB are put in the right places
        rte = RoutingTableEntry({}, 0x0, 0x1)
        assert "X"*31 + "0" in str(rte)

        rte = RoutingTableEntry({}, 0x80000000, 0x80000000)
        assert "1" + "X"*31 in str(rte)

        # Use "!" for bits that could never match
        rte = RoutingTableEntry({}, 0xffffffff, 0x00000000)
        assert "!"*32 in str(rte)

        # Check that the routes are reported correctly
        rte = RoutingTableEntry({Routes.core(1), Routes.east, Routes.south},
                                0x0, 0x0)
        assert "E S 1" in str(rte)


def test_routes():
    # Make sure Links are cast correctly
    assert Routes.east is Routes(Links.east)
    assert Routes.north_east is Routes(Links.north_east)
    assert Routes.north is Routes(Links.north)
    assert Routes.west is Routes(Links.west)
    assert Routes.south_west is Routes(Links.south_west)
    assert Routes.south is Routes(Links.south)

    # Make sure core lookup works correctly
    assert Routes.core(0) is Routes.core_monitor
    assert Routes.core(1) is Routes.core_1
    assert Routes.core(2) is Routes.core_2
    assert Routes.core(3) is Routes.core_3
    assert Routes.core(4) is Routes.core_4
    assert Routes.core(5) is Routes.core_5
    assert Routes.core(6) is Routes.core_6
    assert Routes.core(7) is Routes.core_7
    assert Routes.core(8) is Routes.core_8
    assert Routes.core(9) is Routes.core_9
    assert Routes.core(10) is Routes.core_10
    assert Routes.core(11) is Routes.core_11
    assert Routes.core(12) is Routes.core_12
    assert Routes.core(13) is Routes.core_13
    assert Routes.core(14) is Routes.core_14
    assert Routes.core(15) is Routes.core_15
    assert Routes.core(16) is Routes.core_16
    assert Routes.core(17) is Routes.core_17

    # Make sure route type methods work
    for link in Links:
        assert Routes(link).is_link
        assert not Routes(link).is_core
    for core_num in range(18):
        assert not Routes.core(core_num).is_link
        assert Routes.core(core_num).is_core

    # Lookups out of range should fail
    with pytest.raises(ValueError):
        Routes.core(-1)
    with pytest.raises(ValueError):
        Routes.core(18)

    # The core number property should work
    for core_num in range(18):
        assert Routes.core(core_num).core_num == core_num

    # But should fail for links
    for link in Links:
        with pytest.raises(ValueError):
            Routes(link).core_num

    # Make sure the short strings for routes are correct
    assert Routes.east.initial == "E"
    assert Routes.north_east.initial == "NE"
    assert Routes.north.initial == "N"
    assert Routes.west.initial == "W"
    assert Routes.south_west.initial == "SW"
    assert Routes.south.initial == "S"
    for i in range(18):
        assert Routes.core(i).initial == str(i)
