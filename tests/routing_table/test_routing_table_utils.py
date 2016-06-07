import pytest
from rig.netlist import Net
from rig.place_and_route.routing_tree import RoutingTree
from rig.machine_control.machine_controller import SystemInfo, ChipInfo
from rig.routing_table import RoutingTableEntry, Routes, MultisourceRouteError
from rig.routing_table.utils import (
    routing_tree_to_tables, get_common_xs, expand_entry, expand_entries,
    table_is_subset_of, build_routing_table_target_lengths
)
import warnings


def test_routing_tree_to_tables():
    # Null task
    assert routing_tree_to_tables({}, {}) == {}

    # Single net with a singleton route ending in nothing.
    net = Net(object(), object())
    routes = {net: RoutingTree((0, 0))}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(0, 0): [
            RoutingTableEntry(set(), 0xDEAD, 0xBEEF, {None})
        ]}

    # Single net with a singleton route ending in a number of links.
    net = Net(object(), object())
    routes = {net: RoutingTree((1, 1), [(Routes.north, object()),
                                        (Routes.core_1, object())])}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(1, 1): [
            RoutingTableEntry(set([Routes.north, Routes.core_1]),
                              0xDEAD, 0xBEEF, {None})
        ]}

    # Single net with a singleton route ending in a vertex without a link
    # direction specified should result in a terminus being added but nothing
    # else.
    net = Net(object(), object())
    routes = {net: RoutingTree((1, 1), [(None, object())])}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(1, 1): [RoutingTableEntry(set([]), 0xDEAD, 0xBEEF, {None})]}

    # Single net with a multi-element route
    net = Net(object(), object())
    routes = {net: RoutingTree((1, 1),
                               [(Routes.core_1, object()),
                                (Routes.east,
                                 RoutingTree((2, 1),
                                             [(Routes.core_2,
                                               object())]))])}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(1, 1): [RoutingTableEntry(set([Routes.east, Routes.core_1]),
                  0xDEAD, 0xBEEF, {None})],
         (2, 1): [RoutingTableEntry(set([Routes.core_2]),
                  0xDEAD, 0xBEEF, {Routes.west})]}

    # Single net with a wrapping route
    net = Net(object(), object())
    routes = {net: RoutingTree((7, 1),
                               [(Routes.core_1, net.source),
                                (Routes.east,
                                 RoutingTree((0, 1),
                                             [(Routes.core_2,
                                               net.sinks[0])]))])}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(7, 1): [RoutingTableEntry(set([Routes.east, Routes.core_1]),
                  0xDEAD, 0xBEEF, {None})],
         (0, 1): [RoutingTableEntry(set([Routes.core_2]),
                  0xDEAD, 0xBEEF, {Routes.west})]}

    # Single net with a multi-hop route with no direction changes, terminating
    # in nothing
    net = Net(object(), object())
    r3 = RoutingTree((3, 0))
    r2 = RoutingTree((2, 0), [(Routes.east, r3)])
    r1 = RoutingTree((1, 0), [(Routes.east, r2)])
    r0 = RoutingTree((0, 0), [(Routes.east, r1)])
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF)],
         (1, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (2, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (3, 0): [RoutingTableEntry(set(), 0xDEAD, 0xBEEF, {Routes.west})]}

    # Single net with a multi-hop route with no direction changes, terminating
    # in a number of cores
    net = Net(object(), object())
    r3 = RoutingTree((3, 0), [(Routes.core_2, net.sinks[0]),
                              (Routes.core_3, net.sinks[0])])
    r2 = RoutingTree((2, 0), [(Routes.east, r3)])
    r1 = RoutingTree((1, 0), [(Routes.east, r2)])
    r0 = RoutingTree((0, 0), [(Routes.east, r1)])
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF,
                                    {None})],
         (1, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (2, 0): [RoutingTableEntry(set([Routes.east]), 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (3, 0): [RoutingTableEntry(set([Routes.core_2, Routes.core_3]),
                                    0xDEAD, 0xBEEF, {Routes.west})]
         }

    # Single net with a multi-hop route with a fork in the middle
    net = Net(object(), object())
    r6 = RoutingTree((3, 1), [(Routes.core_6, net.sinks[0])])
    r5 = RoutingTree((5, 0), [(Routes.core_5, net.sinks[0])])
    r4 = RoutingTree((4, 0), [(Routes.east, r5)])
    r3 = RoutingTree((3, 0), [(Routes.east, r4), (Routes.north, r6)])
    r2 = RoutingTree((2, 0), [(Routes.east, r3)])
    r1 = RoutingTree((1, 0), [(Routes.east, r2)])
    r0 = RoutingTree((0, 0), [(Routes.east, r1)])
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}
    assert routing_tree_to_tables(routes, net_keys) == \
        {(0, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF)],
         (1, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (2, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (3, 0): [RoutingTableEntry({Routes.north, Routes.east},
                                    0xDEAD, 0xBEEF, {Routes.west})],
         (4, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (5, 0): [RoutingTableEntry({Routes.core_5}, 0xDEAD, 0xBEEF,
                                    {Routes.west})],
         (3, 1): [RoutingTableEntry({Routes.core_6}, 0xDEAD, 0xBEEF,
                                    {Routes.south})]}

    # Multiple nets
    net0 = Net(object(), object())
    net1 = Net(object(), object())
    routes = {net0: RoutingTree((2, 2), [(Routes.core_1, net0.sinks[0])]),
              net1: RoutingTree((2, 2), [(Routes.core_2, net1.sinks[0])])}
    net_keys = {net0: (0xDEAD, 0xBEEF), net1: (0x1234, 0xABCD)}
    tables = routing_tree_to_tables(routes, net_keys)
    assert set(tables) == set([(2, 2)])
    entries = tables[(2, 2)]
    e0 = RoutingTableEntry(set([Routes.core_1]), 0xDEAD, 0xBEEF)
    e1 = RoutingTableEntry(set([Routes.core_2]), 0x1234, 0xABCD)
    assert entries == [e0, e1] or entries == [e1, e0]


def test_routing_tree_to_tables_repeated_key_mask_merge_allowed():
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
    r0 = RoutingTree((2, 1), [(Routes.core(1), sink)])
    r1 = RoutingTree((1, 1), [(Routes.east, r0)])
    routes = {
        net0: RoutingTree((0, 1), [(Routes.east, r1)]),
        net1: RoutingTree((1, 0), [(Routes.north, r1)]),
    }

    # Create the keys
    net_keys = {net: (0x0, 0xf) for net in (net0, net1)}

    # Build the routing tables
    routing_tables = routing_tree_to_tables(routes, net_keys)

    # Check that the routing tables are correct
    assert routing_tables[(0, 1)] == [
        RoutingTableEntry({Routes.east}, 0x0, 0xf),
    ]
    assert routing_tables[(1, 1)] == [
        RoutingTableEntry({Routes.east}, 0x0, 0xf,
                          {Routes.south, Routes.west}),
    ]
    assert routing_tables[(2, 1)] == [
        RoutingTableEntry({Routes.core(1)}, 0x0, 0xf, {Routes.west}),
    ]
    assert routing_tables[(1, 0)] == [
        RoutingTableEntry({Routes.north}, 0x0, 0xf),
    ]


def test_routing_tree_to_tables_repeated_key_mask_fork_not_allowed():
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
    r_east = RoutingTree((2, 1), [(Routes.core(1), sink0)])
    routes = {
        net0: RoutingTree((0, 1), [
            (Routes.east, RoutingTree((1, 1), [(Routes.east, r_east)])),
        ]),
        net1: RoutingTree((1, 1), [
            (Routes.east, r_east),
            (Routes.south, RoutingTree((1, 0), [(Routes.core(1), sink1)])),
        ]),
    }

    # Create the keys
    net_keys = {net: (0x0, 0xf) for net in (net0, net1)}

    # Build the routing tables
    with pytest.raises(MultisourceRouteError) as err:
        routing_tree_to_tables(routes, net_keys)

    assert "(1, 1)" in str(err)  # Co-ordinate of the fork
    assert "0x00000000" in str(err)  # Key that causes the problem
    assert "0x0000000f" in str(err)  # Mask that causes the problem


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


def test_get_common_xs():
    # Common X in the LSB only as other Xs exist only in one entry
    entries = [
        RoutingTableEntry({Routes.north}, 0b0100, 0xfffffff0 | 0b1100),  # 01XX
        RoutingTableEntry({Routes.north}, 0b0010, 0xfffffff0 | 0b0010),  # XX1X
    ]
    assert get_common_xs(entries) == 0x00000001

    # Common Xs in the MSB bit 2
    RTE = RoutingTableEntry
    entries = [
        RTE({Routes.north}, 0b0100, 0x7ffffff0 | 0b1101),  # X...01X0
        RTE({Routes.north}, 0b0001, 0x7ffffff0 | 0b0001),  # X...XXX1
    ]
    assert get_common_xs(entries) == 0x80000002


def test_expand_entry():
    RTE = RoutingTableEntry
    # There is one X in the entry, this should result in two new entries being
    # returned with the X set to `0' and `1' respectively.
    entry = RTE({Routes.north}, 0x0, 0xfffffffe)
    assert list(expand_entry(entry)) == [
        RTE({Routes.north}, 0x0, 0xffffffff),
        RTE({Routes.north}, 0x1, 0xffffffff),
    ]

    # The same, but ensuring that the source information isn't lost.
    entry = RTE({Routes.north}, 0x0, 0xfffffffe, {Routes.south})
    assert list(expand_entry(entry)) == [
        RTE({Routes.north}, 0x0, 0xffffffff, {Routes.south}),
        RTE({Routes.north}, 0x1, 0xffffffff, {Routes.south}),
    ]

    # There are 3 Xs, but we only allow two of them to be expanded
    entry = RTE({Routes.north}, 0x0, 0xfffffff8)
    assert list(expand_entry(entry, ignore_xs=0x4)) == [
        RTE({Routes.north}, 0x0, 0xfffffffb),
        RTE({Routes.north}, 0x1, 0xfffffffb),
        RTE({Routes.north}, 0x2, 0xfffffffb),
        RTE({Routes.north}, 0x3, 0xfffffffb),
    ]


def test_expand_entries_expands_entries():
    # Test that each entry is expanded in order
    entries = [
        RoutingTableEntry({Routes.north}, 0x0, 0xfffffffe),  # 000X
        RoutingTableEntry({Routes.north}, 0x4, 0xfffffffd),  # 01X0
    ]
    assert list(expand_entries(entries)) == [
        RoutingTableEntry({Routes.north}, 0x0, 0xffffffff),
        RoutingTableEntry({Routes.north}, 0x1, 0xffffffff),
        RoutingTableEntry({Routes.north}, 0x4, 0xffffffff),
        RoutingTableEntry({Routes.north}, 0x6, 0xffffffff),
    ]


def test_expand_entries_ignores_common_xs():
    # Test that each entry is expanded in order, but that Xs common to all
    # entries are ignored.
    entries = [
        RoutingTableEntry({Routes.north}, 0x0, 0x0000000e),  # 000X
        RoutingTableEntry({Routes.north}, 0x4, 0x0000000d),  # 01X0
    ]
    assert list(expand_entries(entries)) == [
        RoutingTableEntry({Routes.north}, 0x0, 0x0000000f),
        RoutingTableEntry({Routes.north}, 0x1, 0x0000000f),
        RoutingTableEntry({Routes.north}, 0x4, 0x0000000f),
        RoutingTableEntry({Routes.north}, 0x6, 0x0000000f),
    ]


def test_expand_entries_ignores_supplied_xs():
    # Test that each entry is expanded in order, but that Xs we specify are
    # ignored.
    entries = [
        RoutingTableEntry({Routes.north}, 0x0, 0x0000000e),  # 000X
        RoutingTableEntry({Routes.north}, 0x4, 0x00000005),  # X1X0
    ]
    assert list(expand_entries(entries, ignore_xs=0xfffffff8)) == [
        RoutingTableEntry({Routes.north}, 0x0, 0x0000000f),
        RoutingTableEntry({Routes.north}, 0x1, 0x0000000f),
        RoutingTableEntry({Routes.north}, 0x4, 0x00000007),
        RoutingTableEntry({Routes.north}, 0x6, 0x00000007),
    ]


def test_expand_entries_guarantess_orthogonality():
    # Test that the resulting table is orthogonal and that a warning about
    # non-orthogonality is raised.
    entries = [
        RoutingTableEntry({Routes.north}, 0x80000000, 0xfffffffe),  # 1...000X
        RoutingTableEntry({Routes.north}, 0x80000000, 0xfffffffd),  # 1...00X0
    ]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        new_entries = list(expand_entries(entries))
        assert len(w) == 1
        assert "Key 0x80000000" in str(w[0])

    assert new_entries == [
        RoutingTableEntry({Routes.north}, 0x80000000, 0xffffffff),
        RoutingTableEntry({Routes.north}, 0x80000001, 0xffffffff),
        RoutingTableEntry({Routes.north}, 0x80000002, 0xffffffff),
    ]


def test_table_is_subset_of_different_routes():
    # Test that if a different route is the result of the same key that tables
    # are not reported as subsets.
    entries_a = [RoutingTableEntry({Routes.north}, 0x0, 0xffffffff),
                 RoutingTableEntry({Routes.west}, 0x1, 0xffffffff)]
    entries_b = [RoutingTableEntry({Routes.north}, 0x0, 0x0)]
    assert not table_is_subset_of(entries_a, entries_b)


def test_table_is_subset_of_no_match():
    # Test that if one table doesn't match an entry from the first they are not
    # reported as subsets.
    entries_a = [RoutingTableEntry({Routes.north}, 0x0, 0xffffffff),
                 RoutingTableEntry({Routes.west}, 0x1, 0xffffffff)]
    entries_b = [RoutingTableEntry({Routes.north}, 0x8, 0x8)]
    assert not table_is_subset_of(entries_a, entries_b)


def test_table_is_subset_of_default_route():
    # Test that subsets are identified if the second table relies on default
    # routes to work
    entries_a = [RoutingTableEntry({Routes.north}, 0x0, 0xffffffff,
                                   {Routes.south}),  # Can be default routed
                 RoutingTableEntry({Routes.west}, 0x1, 0xffffffff)]
    entries_b = [entries_a[-1]]
    assert table_is_subset_of(entries_a, entries_b)

    entries_a = [RoutingTableEntry({Routes.north}, 0x0, 0xffffffff,
                                   {Routes.south, Routes.west}),
                 RoutingTableEntry({Routes.west}, 0x1, 0xffffffff)]
    entries_b = [entries_a[-1]]
    assert not table_is_subset_of(entries_a, entries_b)

    entries_a = [RoutingTableEntry({Routes.north}, 0x0, 0xffffffff,
                                   {Routes.core(3)}),
                 RoutingTableEntry({Routes.west}, 0x1, 0xffffffff)]
    entries_b = [entries_a[-1]]
    assert not table_is_subset_of(entries_a, entries_b)


def test_table_is_subset_of_uses_common_xs_of_other_table():
    entries_a = [RoutingTableEntry({Routes.west}, 0x0, 0xfffffffe),
                 RoutingTableEntry({Routes.west}, 0x0, 0xfffffffc)]
    entries_b = [RoutingTableEntry({Routes.west}, 0x0, 0xffffffff),
                 RoutingTableEntry({Routes.west}, 0x2, 0xfffffffe)]
    assert not table_is_subset_of(entries_a, entries_b)


def test_table_is_subset_of_success():
    entries_a = [RoutingTableEntry({Routes.north}, 0x0, 0xffffffff),
                 RoutingTableEntry({Routes.west}, 0x1, 0xffffffff)]
    entries_b = [RoutingTableEntry({Routes.west}, 0x1, 0x00000001),
                 RoutingTableEntry({Routes.north}, 0x0, 0x00000000)]
    assert table_is_subset_of(entries_a, entries_b)
