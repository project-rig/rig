import pytest

from rig.links import Links

from rig.routing_table import Routes, RoutingTableEntry, RouteSet


class TestRouteSet(object):
    def test_or_update_and_contains_and_len(self):
        # Create an empty route set
        rs = RouteSet()
        assert len(rs) == 0

        # Include east
        rs |= {Routes.east}
        assert len(rs) == 1
        assert set(rs) == {Routes.east}
        assert Routes.east in rs

        # Include north east
        rs |= {Routes.north_east}
        assert len(rs) == 2
        assert set(rs) == {Routes.east, Routes.north_east}
        assert Routes.north_east in rs
        assert not Routes.north in rs

        # Shouldn't do anything
        rs |= {Routes.north_east}
        assert len(rs) == 2
        assert set(rs) == {Routes.east, Routes.north_east}
        assert Routes.north_east in rs
        assert not Routes.south in rs
        assert not None in rs

        # Check that None works
        rs |= {Routes.south, None}
        assert len(rs) == 4
        assert set(rs) == {Routes.east, Routes.north_east, Routes.south, None}
        assert None in rs

        rs |= Routes
        assert len(rs) == 25

    def test_remove(self):
        rs = RouteSet(Routes)

        rs -= {Routes.north, Routes.south}
        assert len(rs) == 22
        assert Routes.north not in rs
        assert Routes.south not in rs

    def test_equality(self):
        assert RouteSet({Routes.north}) == RouteSet({Routes.north})
        assert RouteSet({None}) != RouteSet()
        assert RouteSet({None}) != RouteSet({Routes.south_west})
        assert RouteSet({None}) == RouteSet({None})
        assert RouteSet({Routes.north}) != RouteSet({Routes.south})
        assert RouteSet(Routes) != RouteSet()

        assert RouteSet({Routes.north}) == {Routes.north}
        assert RouteSet({None}) != set()
        assert RouteSet({None}) != {Routes.south_west}
        assert RouteSet({None}) == {None}
        assert RouteSet({Routes.north}) != {Routes.south}
        assert RouteSet(Routes) != set()

    def test_int(self):
        for r in Routes:
            rs = RouteSet({r})
            assert int(rs) == 1 << r

        assert int(RouteSet({None})) == 0x80000000


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

    def test_str_with_source(self):
        RTE = RoutingTableEntry

        assert (str(RTE({Routes.core(3)}, 0x0, 0x0, {Routes.east})) ==
                "E -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")
        assert (str(RTE({Routes.core(3)}, 0x0, 0x0, {Routes.north_east})) ==
                "NE -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")
        assert (str(RTE({Routes.core(3)}, 0x0, 0x0, {Routes.north})) ==
                "N -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")
        assert (str(RTE({Routes.core(3)}, 0x0, 0x0, {Routes.west})) ==
                "W -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")
        assert (str(RTE({Routes.core(3)}, 0x0, 0x0, {Routes.south_west})) ==
                "SW -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")
        assert (str(RTE({Routes.core(3)}, 0x0, 0x0, {Routes.south})) ==
                "S -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")
        assert (str(RTE({Routes.core(2)}, 0x0, 0x0, {Routes.core(1)})) ==
                "1 -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 2")

        # Check multiple
        assert (str(RTE({Routes.core(3)}, 0x0, 0x0,
                        {Routes.west, Routes.south})) ==
                "W S -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")

        # Check that it works even if a None bleeds in
        assert (str(RTE({Routes.core(3)}, 0x0, 0x0,
                        {Routes.west, Routes.south, None})) ==
                "W S -> XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 3")


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

    # Test that the opposites are correct
    assert Routes.east.opposite is Routes.west
    assert Routes.north_east.opposite is Routes.south_west
    assert Routes.north.opposite is Routes.south
    assert Routes.east is Routes.west.opposite
    assert Routes.north_east is Routes.south_west.opposite
    assert Routes.north is Routes.south.opposite

    for i in range(18):
        with pytest.raises(ValueError):
            Routes.core(i).opposite
