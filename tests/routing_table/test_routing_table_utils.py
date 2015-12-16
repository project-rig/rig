import warnings

from rig.routing_table import RoutingTableEntry
from rig.routing_table.utils import (
    get_common_xs, expand_entry, expand_entries, table_is_subset_of
)


def test_get_common_xs():
    # Common X in the LSB only as other Xs exist only in one entry
    entries = [
        RoutingTableEntry(None, 0b0100, 0xfffffff0 | 0b1100),  # 01XX
        RoutingTableEntry(None, 0b0010, 0xfffffff0 | 0b0010),  # XX1X
    ]
    assert get_common_xs(entries) == 0x00000001

    # Common Xs in the MSB bit 2
    entries = [
        RoutingTableEntry(None, 0b0100, 0x7ffffff0 | 0b1101),  # X...01X0
        RoutingTableEntry(None, 0b0001, 0x7ffffff0 | 0b0001),  # X...XXX1
    ]
    assert get_common_xs(entries) == 0x80000002


def test_expand_entry():
    # There is one X in the entry, this should result in two new entries being
    # returned with the X set to `0' and `1' respectively.
    entry = RoutingTableEntry(None, 0x0, 0xfffffffe)
    assert list(expand_entry(entry)) == [
        RoutingTableEntry(None, 0x0, 0xffffffff),
        RoutingTableEntry(None, 0x1, 0xffffffff),
    ]

    # There are 3 Xs, but we only allow two of them to be expanded
    entry = RoutingTableEntry(None, 0x0, 0xfffffff8)
    assert list(expand_entry(entry, ignore_xs=0x4)) == [
        RoutingTableEntry(None, 0x0, 0xfffffffb),
        RoutingTableEntry(None, 0x1, 0xfffffffb),
        RoutingTableEntry(None, 0x2, 0xfffffffb),
        RoutingTableEntry(None, 0x3, 0xfffffffb),
    ]


def test_expand_entries_expands_entries():
    # Test that each entry is expanded in order
    entries = [
        RoutingTableEntry(None, 0x0, 0xfffffffe),  # 000X
        RoutingTableEntry(None, 0x4, 0xfffffffd),  # 01X0
    ]
    assert list(expand_entries(entries)) == [
        RoutingTableEntry(None, 0x0, 0xffffffff),
        RoutingTableEntry(None, 0x1, 0xffffffff),
        RoutingTableEntry(None, 0x4, 0xffffffff),
        RoutingTableEntry(None, 0x6, 0xffffffff),
    ]


def test_expand_entries_ignores_common_xs():
    # Test that each entry is expanded in order, but that Xs common to all
    # entries are ignored.
    entries = [
        RoutingTableEntry(None, 0x0, 0x0000000e),  # 000X
        RoutingTableEntry(None, 0x4, 0x0000000d),  # 01X0
    ]
    assert list(expand_entries(entries)) == [
        RoutingTableEntry(None, 0x0, 0x0000000f),
        RoutingTableEntry(None, 0x1, 0x0000000f),
        RoutingTableEntry(None, 0x4, 0x0000000f),
        RoutingTableEntry(None, 0x6, 0x0000000f),
    ]


def test_expand_entries_ignores_supplied_xs():
    # Test that each entry is expanded in order, but that Xs we specify are
    # ignored.
    entries = [
        RoutingTableEntry(None, 0x0, 0x0000000e),  # 000X
        RoutingTableEntry(None, 0x4, 0x00000005),  # X1X0
    ]
    assert list(expand_entries(entries, ignore_xs=0xfffffff8)) == [
        RoutingTableEntry(None, 0x0, 0x0000000f),
        RoutingTableEntry(None, 0x1, 0x0000000f),
        RoutingTableEntry(None, 0x4, 0x00000007),
        RoutingTableEntry(None, 0x6, 0x00000007),
    ]


def test_expand_entries_guarantess_orthogonality():
    # Test that the resulting table is orthogonal and that a warning about
    # non-orthogonality is raised.
    entries = [
        RoutingTableEntry(None, 0x80000000, 0xfffffffe),  # 1...000X
        RoutingTableEntry(None, 0x80000000, 0xfffffffd),  # 1...00X0
    ]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        new_entries = list(expand_entries(entries))
        assert len(w) == 1
        assert "Key 0x80000000" in str(w[0])

    assert new_entries == [
        RoutingTableEntry(None, 0x80000000, 0xffffffff),
        RoutingTableEntry(None, 0x80000001, 0xffffffff),
        RoutingTableEntry(None, 0x80000002, 0xffffffff),
    ]


def test_table_is_subset_of_different_routes():
    # Test that if a different route is the result of the same key that tables
    # are not reported as subsets.
    entries_a = [RoutingTableEntry(1, 0x0, 0xffffffff),
                 RoutingTableEntry(0, 0x1, 0xffffffff)]
    entries_b = [RoutingTableEntry(1, 0x0, 0x0)]
    assert not table_is_subset_of(entries_a, entries_b)


def test_table_is_subset_of_no_match():
    # Test that if one table doesn't match an entry from the first they are not
    # reported as subsets.
    entries_a = [RoutingTableEntry(1, 0x0, 0xffffffff),
                 RoutingTableEntry(0, 0x1, 0xffffffff)]
    entries_b = [RoutingTableEntry(1, 0x8, 0x8)]
    assert not table_is_subset_of(entries_a, entries_b)


def test_table_is_subset_of_uses_common_xs_of_other_table():
    entries_a = [RoutingTableEntry(0, 0x0, 0xfffffffe),
                 RoutingTableEntry(0, 0x0, 0xfffffffc)]
    entries_b = [RoutingTableEntry(0, 0x0, 0xffffffff),
                 RoutingTableEntry(0, 0x2, 0xfffffffe)]
    assert not table_is_subset_of(entries_a, entries_b)


def test_table_is_subset_of_success():
    entries_a = [RoutingTableEntry(1, 0x0, 0xffffffff),
                 RoutingTableEntry(0, 0x1, 0xffffffff)]
    entries_b = [RoutingTableEntry(0, 0x1, 0x00000001),
                 RoutingTableEntry(1, 0x0, 0x00000000)]
    assert table_is_subset_of(entries_a, entries_b)
