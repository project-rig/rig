from rig.place_and_route.util import build_application_map, \
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

    # The same but this time forcing intermediate hops to be included
    net = Net(object(), object())
    r3 = RoutingTree((3, 0))
    r2 = RoutingTree((2, 0), set([r3]))
    r1 = RoutingTree((1, 0), set([r2]))
    r0 = RoutingTree((0, 0), set([r1]))
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
