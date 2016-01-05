import pytest

from collections import defaultdict

from rig.place_and_route.utils import \
    build_machine, build_core_constraints, build_application_map, \
    build_routing_tables, MultisourceRouteError, \
    _get_minimal_core_reservations, \
    build_and_minimise_routing_tables, \
    build_routing_table_target_lengths

from rig.place_and_route.machine import Machine, Cores

from rig.links import Links

from rig.netlist import Net

from rig.routing_table import (
    Routes, RoutingTableEntry, MinimisationFailedError)

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


@pytest.mark.parametrize(
    "cores,expected_slices",
    [
        # Special case: No reservations!
        ([], []),
        # Singletons
        ([0], [slice(0, 1)]),
        ([1], [slice(1, 2)]),
        ([17], [slice(17, 18)]),
        # Contiguous ranges
        ([0, 1], [slice(0, 2)]),
        ([3, 4, 5, 6], [slice(3, 7)]),
        # Multiple, disjoint ranges
        ([0, 2, 3], [slice(0, 1), slice(2, 4)]),
        ([0, 1, 16, 17], [slice(0, 2), slice(16, 18)]),
    ])
def test__get_minimal_core_reservations(cores, expected_slices):
    reservations = _get_minimal_core_reservations("MyCores", cores, (1, 2))
    assert [r.reservation for r in reservations] == expected_slices


@pytest.mark.parametrize("global_core_0", [False, True])
def test_build_core_constraints(global_core_0):
    # * A 4x1 machine
    # * (1, 0) has 17 cores, the rest 18
    # * All 18-core chips have a busy core 17
    # * All chips have a cores 0-(x+1) busy if global_core_0 else 1-(x+1)
    system_info = SystemInfo(4, 1, {
        (x, y): ChipInfo(
            num_cores=(17 if (x, y) == (1, 0) else 18),
            core_states=[(AppState.run
                          if ((0 if global_core_0 else 1) <= c <= x
                              or c == 17)
                          else AppState.idle)
                         for c in range(17 if (x, y) == (1, 0) else 18)],
            working_links=set(Links),
            largest_free_sdram_block=100,
            largest_free_sram_block=10,
        )
        for x in range(4)
        for y in range(1)
    })

    constraints = build_core_constraints(system_info, "MyCores")

    # Should end up with:
    # * 1 global constraint (if global_core_0)
    # * 1 constraint on chips x=1 to 3 for the unique reservation
    # * 1 constraint on chips x=0, 2 and 3 to reserve core 18
    assert len(constraints) == (7 if global_core_0 else 6)

    # All constraints must reserve cores
    assert all(isinstance(c, ReserveResourceConstraint)
               for c in constraints)
    assert all(c.resource == "MyCores" for c in constraints)

    # The first constraint must be the global reservation
    if global_core_0:
        global_reservation = constraints.pop(0)
        assert global_reservation.reservation == slice(0, 1)
        assert global_reservation.location is None

    # The remaining constraints should cover those expected above
    # A set of (x, y, start, stop) tuples.
    expected_ranges = set([
        # Core 18 reservations
        (0, 0, 17, 18),
        (2, 0, 17, 18),
        (3, 0, 17, 18),

        # Other reservations
        (1, 0, 1, 2),
        (2, 0, 1, 3),
        (3, 0, 1, 4),
    ])
    for constraint in constraints:
        assert constraint.location is not None
        x, y = constraint.location
        expected_ranges.remove((
            x, y,
            constraint.reservation.start,
            constraint.reservation.stop))
    assert len(expected_ranges) == 0


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


def test_build_minimised_routing_tables():
    """Test building and minimising routing tables.

    Key 0000:

                    (1, 1)
                      ^
                      |
                      |
        (0, 0) ---> (0, 1)

    Key 0011:

                    (1, 1)
                      ^
                      |
                      |
                    (0, 1) <---- (0, 2)

    Key 0001:

        (0, 0) ---> (0, 1) ---> (0, 2)
    """
    # Create the nets and net->key mapping
    nets = [object() for _ in range(3)]
    net_keys = {nets[0]: (0x0, 0xf),
                nets[1]: (0x3, 0xf),
                nets[2]: (0x1, 0xf)}

    # Create the routing trees
    routes = {
        nets[0]: RoutingTree((0, 0), {
            (Routes.east, RoutingTree((0, 1), {
                (Routes.north, RoutingTree((1, 1), {
                    (Routes.core(1), object())
                }))
            }))
        }),
        nets[1]: RoutingTree((0, 2), {
            (Routes.west, RoutingTree((0, 1), {
                (Routes.north, RoutingTree((1, 1), {
                    (Routes.core(1), object())
                }))
            }))
        }),
        nets[2]: RoutingTree((0, 0), {
            (Routes.east, RoutingTree((0, 1), {
                (Routes.east, RoutingTree((0, 2), {
                    (Routes.core(1), object())
                }))
            }))
        }),
    }

    # Get the routing tables, with no minimisation
    routing_tables = build_and_minimise_routing_tables(
        routes, net_keys, 1024)

    # Check at (0, 0)
    e0 = RoutingTableEntry({Routes.east}, 0x0, 0xf)
    e1 = RoutingTableEntry({Routes.east}, 0x1, 0xf)
    assert (routing_tables[(0, 0)] == [e0, e1] or
            routing_tables[(0, 0)] == [e1, e0])

    # Check at (0, 1)
    e0 = RoutingTableEntry({Routes.north}, 0x0, 0xf)
    e1 = RoutingTableEntry({Routes.east}, 0x1, 0xf)
    e2 = RoutingTableEntry({Routes.north}, 0x3, 0xf)
    assert (routing_tables[(0, 1)] == [e0, e1, e2] or
            routing_tables[(0, 1)] == [e0, e2, e1] or
            routing_tables[(0, 1)] == [e1, e0, e2] or
            routing_tables[(0, 1)] == [e1, e2, e0] or
            routing_tables[(0, 1)] == [e2, e0, e1] or
            routing_tables[(0, 1)] == [e2, e1, e0])

    # Check at (0, 2)
    e0 = RoutingTableEntry({Routes.core(1)}, 0x1, 0xf)
    e1 = RoutingTableEntry({Routes.west}, 0x3, 0xf)
    assert (routing_tables[(0, 2)] == [e0, e1] or
            routing_tables[(0, 2)] == [e1, e0])

    # Check at (1, 1)
    e0 = RoutingTableEntry({Routes.core(1)}, 0x0, 0xf)
    e1 = RoutingTableEntry({Routes.core(1)}, 0x3, 0xf)
    assert (routing_tables[(1, 1)] == [e0, e1] or
            routing_tables[(1, 1)] == [e1, e0])

    # Minimise down to 2 entries max
    routing_tables = build_and_minimise_routing_tables(
        routes, net_keys, target_length=2)

    # Check at (0, 0)
    e0 = RoutingTableEntry({Routes.east}, 0x0, 0xf)
    e1 = RoutingTableEntry({Routes.east}, 0x1, 0xf)
    assert (routing_tables[(0, 0)] == [e0, e1] or
            routing_tables[(0, 0)] == [e1, e0])

    # Check at (0, 1) - NOTE: ORDER IS IMPORTANT!
    assert routing_tables[(0, 1)] == [
        RoutingTableEntry({Routes.east}, 0x1, 0xf),
        RoutingTableEntry({Routes.north}, 0x0, 0xc),
    ]

    # Check at (0, 2)
    e0 = RoutingTableEntry({Routes.core(1)}, 0x1, 0xf)
    e1 = RoutingTableEntry({Routes.west}, 0x3, 0xf)
    assert (routing_tables[(0, 2)] == [e0, e1] or
            routing_tables[(0, 2)] == [e1, e0])

    # Check at (1, 1)
    e0 = RoutingTableEntry({Routes.core(1)}, 0x0, 0xf)
    e1 = RoutingTableEntry({Routes.core(1)}, 0x3, 0xf)
    assert (routing_tables[(1, 1)] == [e0, e1] or
            routing_tables[(1, 1)] == [e1, e0])

    # Minimise down to 1 entry max - this is impossible for (0,1) and (0, 2)
    with pytest.raises(MinimisationFailedError) as e:
        build_and_minimise_routing_tables(routes, net_keys, target_length=1)
    assert "(0, 1)" in str(e) or "(0, 2)" in str(e)

    # Minimise down to 1 entry max for chip (0, 1)
    lengths = defaultdict(lambda: 2)  # pragma: no branch (coverage check bug)
    lengths[(0, 1)] = 1
    with pytest.raises(MinimisationFailedError) as e:
        build_and_minimise_routing_tables(routes, net_keys,
                                          target_length=lengths)
    assert "(0, 1)" in str(e)

    # Minimise down to 1 entry max for chip (0, 2)
    lengths = defaultdict(lambda: 2)
    lengths[(0, 2)] = 1
    with pytest.raises(MinimisationFailedError) as e:
        build_and_minimise_routing_tables(routes, net_keys,
                                          target_length=lengths)
    assert "(0, 2)" in str(e)


def test_build_routing_table_target_lengths():
    si = SystemInfo(2, 3, {
        (x, y): ChipInfo(largest_free_rtr_mc_block=(x << 8) | y)
        for x in range(2)
        for y in range(3)
    })
    assert build_routing_table_target_lengths(si) == {  # pragma: no branch
        (x, y): (x << 8) | y
        for x in range(2)
        for y in range(3)
    }
