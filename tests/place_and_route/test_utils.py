from rig.place_and_route.utils import build_application_map, \
    build_routing_tables

from rig.machine import Cores

from rig.netlist import Net

from rig.routing_table import Routes, RoutingTableEntry

from rig.place_and_route.routing_tree import RoutingTree


def test_build_application_map():
    # Test null-case
    assert build_application_map({}, {}, {}) == {}

    # Test with single application on single core
    v = object()
    vertices_applications = {v: "my_app.aplx"}
    placements = {v: (0, 0)}
    allocation = {v: {Cores: slice(1, 2)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1])}}

    # Test with single application on many cores
    v = object()
    vertices_applications = {v: "my_app.aplx"}
    placements = {v: (0, 0)}
    allocation = {v: {Cores: slice(1, 4)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1, 2, 3])}}

    # Test with single application on many chips
    v2 = object()
    v1 = object()
    v0 = object()
    vertices_applications = {v0: "my_app.aplx",
                             v1: "my_app.aplx",
                             v2: "my_app.aplx"}
    placements = {v0: (0, 0), v1: (0, 0), v2: (1, 0)}
    allocation = {v0: {Cores: slice(1, 2)},
                  v1: {Cores: slice(2, 3)},
                  v2: {Cores: slice(1, 2)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1, 2]), (1, 0): set([1])}}

    # Test with multiple applications
    v2 = object()
    v1 = object()
    v0 = object()
    vertices_applications = {v0: "my_app.aplx",
                             v1: "other_app.aplx",
                             v2: "my_app.aplx"}
    placements = {v0: (0, 0), v1: (0, 0), v2: (1, 0)}
    allocation = {v0: {Cores: slice(1, 2)},
                  v1: {Cores: slice(2, 3)},
                  v2: {Cores: slice(1, 2)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1]), (1, 0): set([1])},
         "other_app.aplx": {(0, 0): set([2])}}


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
    routes = {net: RoutingTree((1, 1), set([(Routes.north, object()),
                                            (Routes.core_1, object())]))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(1, 1): [RoutingTableEntry(set([Routes.north, Routes.core_1]),
                  0xDEAD, 0xBEEF)]}

    # Single net with a singleton route ending in a vertex without a link
    # direction specified should result in a terminus being added but nothing
    # else.
    net = Net(object(), object())
    routes = {net: RoutingTree((1, 1), set([(None, object())]))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(1, 1): [RoutingTableEntry(set([]), 0xDEAD, 0xBEEF)]}

    # Single net with a multi-element route
    net = Net(object(), object())
    routes = {net: RoutingTree((1, 1),
                               set([(Routes.core_1, object()),
                                    (Routes.east,
                                     RoutingTree((2, 1),
                                                 set([(Routes.core_2,
                                                       object())])))]))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(1, 1): [RoutingTableEntry(set([Routes.east, Routes.core_1]),
                  0xDEAD, 0xBEEF)],
         (2, 1): [RoutingTableEntry(set([Routes.core_2]),
                  0xDEAD, 0xBEEF)]}

    # Single net with a wrapping route
    net = Net(object(), object())
    routes = {net: RoutingTree((7, 1),
                               set([(Routes.core_1, net.source),
                                    (Routes.east,
                                     RoutingTree((0, 1),
                                                 set([(Routes.core_2,
                                                       net.sinks[0])])))]))}
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
    r2 = RoutingTree((2, 0), set([(Routes.east, r3)]))
    r1 = RoutingTree((1, 0), set([(Routes.east, r2)]))
    r0 = RoutingTree((0, 0), set([(Routes.east, r1)]))
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (3, 0): [RoutingTableEntry(set([]), 0xDEAD, 0xBEEF)]}

    # The same but this time forcing intermediate hops to be included
    net = Net(object(), object())
    r3 = RoutingTree((3, 0))
    r2 = RoutingTree((2, 0), set([(Routes.east, r3)]))
    r1 = RoutingTree((1, 0), set([(Routes.east, r2)]))
    r0 = RoutingTree((0, 0), set([(Routes.east, r1)]))
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys, False) == \
        {(0, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (1, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (2, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (3, 0): [RoutingTableEntry(set([]), 0xDEAD, 0xBEEF)]}

    # Single net with a multi-hop route with no direction changes, terminating
    # in a number of cores
    net = Net(object(), object())
    r3 = RoutingTree((3, 0), set([(Routes.core_2, net.sinks[0]),
                                  (Routes.core_3, net.sinks[0])]))
    r2 = RoutingTree((2, 0), set([(Routes.east, r3)]))
    r1 = RoutingTree((1, 0), set([(Routes.east, r2)]))
    r0 = RoutingTree((0, 0), set([(Routes.east, r1)]))
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert build_routing_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF)],
         (3, 0): [RoutingTableEntry(set([Routes.core_2, Routes.core_3]),
                                    0xDEAD, 0xBEEF)]}

    # Single net with a multi-hop route with a fork in the middle
    net = Net(object(), object())
    r6 = RoutingTree((3, 1), set([(Routes.core_6, net.sinks[0])]))
    r5 = RoutingTree((5, 0), set([(Routes.core_5, net.sinks[0])]))
    r4 = RoutingTree((4, 0), set([(Routes.east, r5)]))
    r3 = RoutingTree((3, 0), set([(Routes.east, r4), (Routes.north, r6)]))
    r2 = RoutingTree((2, 0), set([(Routes.east, r3)]))
    r1 = RoutingTree((1, 0), set([(Routes.east, r2)]))
    r0 = RoutingTree((0, 0), set([(Routes.east, r1)]))
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
    routes = {net0: RoutingTree((2, 2), set([(Routes.core_1, net0.sinks[0])])),
              net1: RoutingTree((2, 2), set([(Routes.core_2, net1.sinks[0])]))}
    net_keys = {net0: (0xDEAD, 0xBEEF), net1: (0x1234, 0xABCD)}
    tables = build_routing_tables(routes, net_keys)
    assert set(tables) == set([(2, 2)])
    entries = tables[(2, 2)]
    e0 = RoutingTableEntry(set([Routes.core_1]), 0xDEAD, 0xBEEF)
    e1 = RoutingTableEntry(set([Routes.core_2]), 0x1234, 0xABCD)
    assert entries == [e0, e1] or entries == [e1, e0]


def test_build_routing_tables_repeated_key_mask():
    # Multiple nets with the same key should be merged together
    n0 = Net(object(), object())
    r0 = RoutingTree((0, 0), set([(Routes.core_6, n0.sinks[0])]))
    n1 = Net(object(), object())
    r1 = RoutingTree((0, 0), set([(Routes.core_5, n1.sinks[0])]))
    routes = {n0: r0, n1: r1}
    net_keys = {n0: (0xCAFE, 0xFFFF), n1: (0xCAFE, 0xFFFF)}
    assert build_routing_tables(routes, net_keys) == {
        (0, 0): [RoutingTableEntry(set([Routes.core_5, Routes.core_6]),
                                   0xCAFE, 0xFFFF)]
    }


def test_build_routing_tables_repeated_key_mask_not_default():
    """The routes illustrated below have the same key and mask but should NOT
    BE marked as default routes, despite the fact that each alone could be.

                (1, 2)
                  ^
                  |
                  |
    (0, 1) ---> (1, 1) ---> (2, 1)
                  ^
                  |
                  |
                (1, 0)
    """
    n0 = Net(object(), object())
    r0 = \
        RoutingTree((0, 1), set([
            (Routes.east, RoutingTree((1, 1), set([
                (Routes.east, RoutingTree((2, 1), set([
                    (Routes.core_1, n0.sinks[0])
                ])))
            ])))
        ]))

    n1 = Net(object(), object())
    r1 = \
        RoutingTree((1, 0), set([
            (Routes.north, RoutingTree((1, 1), set([
                (Routes.north, RoutingTree((1, 2), set([
                    (Routes.core_2, n1.sinks[0])
                ])))
            ])))
        ]))

    routes = {n0: r0, n1: r1}
    net_keys = {n0: (0xCAFE, 0xFFFF), n1: (0xCAFE, 0xFFFF)}

    # Build the routing tables
    routing_tables = build_routing_tables(routes, net_keys)

    assert routing_tables[(0, 1)] == [
        RoutingTableEntry(set([Routes.east]), 0xCAFE, 0xFFFF)]
    assert routing_tables[(1, 0)] == [
        RoutingTableEntry(set([Routes.north]), 0xCAFE, 0xFFFF)]

    assert routing_tables[(2, 1)] == [
        RoutingTableEntry(set([Routes.core_1]), 0xCAFE, 0xFFFF)]
    assert routing_tables[(1, 2)] == [
        RoutingTableEntry(set([Routes.core_2]), 0xCAFE, 0xFFFF)]

    # (1, 1) SHOULD contain 1 entry
    assert routing_tables[(1, 1)] == [
        RoutingTableEntry(set([Routes.east, Routes.north]), 0xCAFE, 0xFFFF)]
