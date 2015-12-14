import pytest

from six import iteritems

from collections import defaultdict

from rig.place_and_route.utils import \
    build_machine, build_core_constraints, build_application_map, \
    build_routing_tables, MultisourceRouteError

from rig.machine import Machine, Links, Cores

from rig.netlist import Net

from rig.routing_table import Routes, RoutingTableEntry

from rig.place_and_route.routing_tree import RoutingTree

from rig.place_and_route.constraints import ReserveResourceConstraint

from rig.machine_control.machine_controller import SystemInfo, ChipInfo

from rig.machine_control.consts import AppState


def test_build_null_machine():
    # Describe a 1x1 machine with all dead chips...
    system_info = SystemInfo(1, 1, {})

    m = build_machine(system_info)

    assert m.width == 1
    assert m.height == 1
    assert m.dead_chips == set([(0, 0)])


def test_build_machine():
    # Describe a 10x8 machine where everything is nominal except:
    # * (0, 1) is dead
    # * (2, 3) has 17 cores, the rest 18
    # * (4, 5) has no north link, all others have working links
    # * (6, 7) has no SDRAM
    # * (7, 6) has no SRAM
    system_info = SystemInfo(10, 8, {
        (x, y): ChipInfo(
            num_cores=(17 if (x, y) == (2, 3) else 18),
            core_states=[AppState.idle
                         if (x, y, c) != (2, 3, 17) else
                         AppState.dead
                         for c in range(17 if (x, y) == (2, 3) else 18)],
            working_links=(set(l for l in Links if l != Links.north)
                           if (x, y) == (4, 5) else
                           set(Links)),
            largest_free_sdram_block=(0 if (x, y) == (6, 7)
                                      else 10 * 1024 * 1024),
            largest_free_sram_block=(0 if (x, y) == (7, 6)
                                     else 1 * 1024 * 1024),
        )
        for x in range(10)
        for y in range(8)
        if (x, y) != (0, 1)
    })

    m = build_machine(system_info,
                      core_resource="MyCores",
                      sdram_resource="MySDRAM",
                      sram_resource="MySRAM")

    # Check that the machine is correct
    assert isinstance(m, Machine)
    assert m.width == 10
    assert m.height == 8
    assert m.chip_resources == {
        "MyCores": 18,
        "MySDRAM": 10 * 1024 * 1024,
        "MySRAM": 1 * 1024 * 1024,
    }
    assert m.chip_resource_exceptions == {
        (2, 3): {
            "MyCores": 17,
            "MySDRAM": 10 * 1024 * 1024,
            "MySRAM": 1 * 1024 * 1024,
        },
        (6, 7): {
            "MyCores": 18,
            "MySDRAM": 0,
            "MySRAM": 1 * 1024 * 1024,
        },
        (7, 6): {
            "MyCores": 18,
            "MySDRAM": 10 * 1024 * 1024,
            "MySRAM": 0,
        },
    }
    assert m.dead_chips == set([(0, 1)])
    assert m.dead_links == set([(4, 5, Links.north)])


def test_build_core_constraints():
    busy_cores = set([
        # Chip 0, 0: Has cores 1-16 (top and bottom reserved)
        (0, 0, 0),
        (0, 0, 17),

        # Chip 1, 0: Has cores 1-16 (bottom reserved, top dead)
        (1, 0, 0),

        # Chip 2, 0: Has cores 1-3 and 5-6 reserved
        (2, 0, 1),
        (2, 0, 2),
        (2, 0, 3),
        (2, 0, 5),
        (2, 0, 6),

        # Chip 3, 0: Has no constraints!
    ])

    # * (1, 0) has 17 cores, the rest 18
    # * Busy cores are taken from the table above
    system_info = SystemInfo(4, 1, {
        (x, y): ChipInfo(
            num_cores=(17 if (x, y) == (1, 0) else 18),
            core_states=[(AppState.idle
                          if (x, y, c) not in busy_cores else
                          AppState.run)
                         for c in range(17 if (x, y) == (0, 1) else 18)],
            working_links=set(Links),
            largest_free_sdram_block=100,
            largest_free_sram_block=10,
        )
        for x in range(4)
        for y in range(1)
    })

    machine = build_machine(system_info, core_resource="MyCores")

    constraints = build_core_constraints(
        system_info, machine, core_resource="MyCores")

    # All constraints should relate to specific chips in the machine
    assert all(c.location is not None for c in constraints)
    assert all(c.location in system_info for c in constraints)

    # All constraints should currently be for cores and SDRAM
    assert all(isinstance(c, ReserveResourceConstraint) for c in constraints)
    assert all(c.resource == "MyCores" for c in constraints)

    # Split constraints by chip and type
    core_constraints = defaultdict(list)
    for constraint in constraints:
        core_constraints[constraint.location].append(constraint)

    # Sort core constraints by starting core
    for chip, constraints_ in iteritems(core_constraints):
        constraints_.sort(key=(lambda c: c.reservation.start))

    # Check correctness and minimality of core reservations
    assert len(core_constraints) == 3

    assert len(core_constraints[(0, 0)]) == 2
    assert core_constraints[(0, 0)][0].reservation == slice(0, 1)
    assert core_constraints[(0, 0)][1].reservation == slice(17, 18)

    assert len(core_constraints[(1, 0)]) == 1
    assert core_constraints[(1, 0)][0].reservation == slice(0, 1)

    assert len(core_constraints[(2, 0)]) == 2
    assert core_constraints[(2, 0)][0].reservation == slice(1, 4)
    assert core_constraints[(2, 0)][1].reservation == slice(5, 7)

    assert len(core_constraints[(3, 0)]) == 0


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


def test_build_routing_tables_repeated_key_mask_merge_allowed():
    """Nets with the same key and mask are allowed to MERGE into a SpiNNaker
    node provided that they have the same outgoing route.


    e.g.,

        (0, 1) ----> (1, 1) ----> (2, 1)

        PLUS:

                     (1, 1) ----> (2, 1)

                       ^
                       |
                       |

                     (1, 0)

        EQUALS:


        (0, 1) ----> (1, 1) ----> (2, 1)

                       ^
                       |
                       |

                     (1, 0)
    """
    # Create the nets
    sink = object()
    net0 = Net(object(), sink)
    net1 = Net(object(), sink)

    # Create the routing trees
    r0 = RoutingTree((2, 1), {(Routes.core(1), sink)})
    r1 = RoutingTree((1, 1), {(Routes.west, r0)})
    routes = {
        net0: RoutingTree((0, 1), {(Routes.west, r1)}),
        net1: RoutingTree((1, 0), {(Routes.north, r1)}),
    }

    # Create the keys
    net_keys = {net: (0x0, 0xf) for net in (net0, net1)}

    # Build the routing tables
    routing_tables = build_routing_tables(routes, net_keys)

    # Check that the routing tables are correct
    assert routing_tables[(0, 1)] == [
        RoutingTableEntry({Routes.west}, 0x0, 0xf),
    ]
    assert routing_tables[(1, 1)] == [
        RoutingTableEntry({Routes.west}, 0x0, 0xf),
    ]
    assert routing_tables[(2, 1)] == [
        RoutingTableEntry({Routes.core(1)}, 0x0, 0xf),
    ]
    assert routing_tables[(1, 0)] == [
        RoutingTableEntry({Routes.north}, 0x0, 0xf),
    ]


def test_build_routing_tables_repeated_key_mask_fork_not_allowed():
    """Two nets with the same key and mask are NEVER allowed to FORK at a
    SpiNNaker node.

    e.g.,

        (0, 1) ----> (1, 1) ----> (2, 1)

        PLUS:

                     (1, 1) ----> (2, 1)

                       |
                       |
                       v

                     (1, 0)

        IS NOT ALLOWED!
    """
    # Create the nets
    sink0 = object()
    sink1 = object()

    net0 = Net(object(), sink0)
    net1 = Net(object(), [sink0, sink1])

    # Create the routing trees
    r_west = RoutingTree((2, 1), {(Routes.core(1), sink0)})
    routes = {
        net0: RoutingTree((0, 1), {
            (Routes.west, RoutingTree((1, 1), {(Routes.west, r_west)})),
        }),
        net1: RoutingTree((1, 1), {
            (Routes.west, r_west),
            (Routes.south, RoutingTree((1, 0), {(Routes.core(1), sink1)})),
        }),
    }

    # Create the keys
    net_keys = {net: (0x0, 0xf) for net in (net0, net1)}

    # Build the routing tables
    with pytest.raises(MultisourceRouteError) as err:
        build_routing_tables(routes, net_keys)

    assert "(1, 1)" in str(err)  # Co-ordinate of the fork
    assert "0x00000000" in str(err)  # Key that causes the problem
    assert "0x0000000f" in str(err)  # Mask that causes the problem
