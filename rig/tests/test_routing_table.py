import pytest

from rig.machine import Links

from rig.routing_table import Routes, RoutingTree, RoutingTableEntry, \
    build_routing_tables

from rig.netlist import Net


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

    # Lookups out of range should fail
    with pytest.raises(Exception):
        Routes.core(-1)
    with pytest.raises(Exception):
        Routes.core(18)


class TestRoutingTree(object):

    def test_init_default(self):
        # Make sure the default initialiser creates no children
        assert RoutingTree((0, 0)).children == set()

    def test_iter(self):
        # Singleton
        t = RoutingTree((0, 0))
        assert set(t) == set([t])

        # Multiple Children
        t2 = RoutingTree((2, 0))
        t1 = RoutingTree((1, 0))
        t0 = RoutingTree((0, 0), set([t1, t2]))
        assert set(t0) == set([t0, t1, t2])

        # Grandchildren
        t2 = RoutingTree((2, 0))
        t1 = RoutingTree((1, 0), set([t2]))
        t0 = RoutingTree((0, 0), set([t1]))
        assert set(t0) == set([t0, t1, t2])

        # Inclusion of other types
        t2 = object()
        t1 = RoutingTree((1, 0), set([t2]))
        t0 = RoutingTree((0, 0), set([t1]))
        assert set(t0) == set([t0, t1, t2])

    def test_repr(self):
        # Sanity check for repr. Human-readable representations should at a
        # minimum include the node's type and location.
        t = RoutingTree((123, 321))
        assert "RoutingTree" in repr(t)
        assert "123" in repr(t)
        assert "321" in repr(t)


def test_build_routing_tables():
    # Null task
    assert build_routing_tables({}, {}) == {}

    # Single net with a singleton route ending in nothing.
    net = Net(object(), object())
    routes = {net: RoutingTree((0, 0))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry(set(), 0xDEAD, 0xBEEF)]}

    # Single net with a singleton route ending in a number of links.
    net = Net(object(), object())
    routes = {net: RoutingTree((1, 1), set([Routes.north, Routes.core_1]))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(1, 1): [RoutingTableEntry(set([Routes.north, Routes.core_1]),
                  0xDEAD, 0xBEEF)]}

    # Single net with a multi-element route
    net = Net(object(), object())
    routes = {net: RoutingTree((1, 1),
                               set([Routes.core_1,
                                    RoutingTree((2, 1),
                                                set([Routes.core_2]))]))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(1, 1): [RoutingTableEntry(set([Routes.east, Routes.core_1]),
                  0xDEAD, 0xBEEF)],
         (2, 1): [RoutingTableEntry(set([Routes.core_2]),
                  0xDEAD, 0xBEEF)]}

    # Single net with a wrapping route
    net = Net(object(), object())
    routes = {net: RoutingTree((7, 1),
                               set([Routes.core_1,
                                    RoutingTree((0, 1),
                                                set([Routes.core_2]))]))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(7, 1): [RoutingTableEntry(set([Routes.east, Routes.core_1]),
                  0xDEAD, 0xBEEF)],
         (0, 1): [RoutingTableEntry(set([Routes.core_2]),
                  0xDEAD, 0xBEEF)]}

    # Single net with a multi-hop route with no direction changes, terminating
    # in nothing
    net = Net(object(), object())
    r3 = RoutingTree((3, 0))
    r2 = RoutingTree((2, 0), set([r3]))
    r1 = RoutingTree((1, 0), set([r2]))
    r0 = RoutingTree((0, 0), set([r1]))
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (3, 0): [RoutingTableEntry(set([]), 0xDEAD, 0xBEEF)]}

    # Single net with a multi-hop route with no direction changes, terminating
    # in a number of cores
    net = Net(object(), object())
    r3 = RoutingTree((3, 0), set([Routes.core_2, Routes.core_3]))
    r2 = RoutingTree((2, 0), set([r3]))
    r1 = RoutingTree((1, 0), set([r2]))
    r0 = RoutingTree((0, 0), set([r1]))
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (3, 0): [RoutingTableEntry(set([Routes.core_2, Routes.core_3]),
                                    0xDEAD, 0xBEEF)]}

    # Single net with a multi-hop route with a fork in the middle
    net = Net(object(), object())
    r6 = RoutingTree((3, 1), set([Routes.core_6]))
    r5 = RoutingTree((5, 0), set([Routes.core_5]))
    r4 = RoutingTree((4, 0), set([r5]))
    r3 = RoutingTree((3, 0), set([r4, r6]))
    r2 = RoutingTree((2, 0), set([r3]))
    r1 = RoutingTree((1, 0), set([r2]))
    r0 = RoutingTree((0, 0), set([r1]))
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (3, 0): [RoutingTableEntry(set([Routes.north, Routes.east]),
                                    0xDEAD, 0xBEEF)],
         (5, 0): [RoutingTableEntry(set([Routes.core_5]), 0xDEAD, 0xBEEF)],
         (3, 1): [RoutingTableEntry(set([Routes.core_6]), 0xDEAD, 0xBEEF)]}

    # Multiple nets
    net0 = Net(object(), object())
    net1 = Net(object(), object())
    routes = {net0: RoutingTree((2, 2), set([Routes.core_1])),
              net1: RoutingTree((2, 2), set([Routes.core_2]))}
    net_keys = {net0: (0xDEAD, 0xBEEF), net1: (0x1234, 0xABCD)}
    tables = build_routing_tables(routes, net_keys)
    assert set(tables) == set([(2, 2)])
    entries = tables[(2, 2)]
    e0 = RoutingTableEntry(set([Routes.core_1]), 0xDEAD, 0xBEEF)
    e1 = RoutingTableEntry(set([Routes.core_2]), 0x1234, 0xABCD)
    assert entries == [e0, e1] or entries == [e1, e0]
