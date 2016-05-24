import pytest
from mock import Mock

from rig.routing_table import (Routes, RoutingTableEntry,
                               MinimisationFailedError)
from rig.routing_table.remove_default_routes import minimise, _is_defaultable
from rig.routing_table import remove_default_routes


def test_minimise_orthogonal_table():
    """Test for correct removal of default routes in an orthogonal table."""
    table = [
        RoutingTableEntry({Routes.north}, 0x0, 0xf, {Routes.south}),  # Remove
        RoutingTableEntry({Routes.north}, 0x1, 0xf, {Routes.north}),  # Keep
        RoutingTableEntry({Routes.north}, 0x2, 0xf, {None}),  # Keep
        RoutingTableEntry({Routes.north, Routes.south}, 0x3, 0xf,
                          {Routes.north, Routes.south}),  # Keep
        RoutingTableEntry({Routes.core(1)}, 0x4, 0xf, {Routes.core(1)})  # Keep
    ]
    assert minimise(table, len(table) - 1) == table[1:]


def test_minimise_nonorthogonal_table():
    """Test for correct removal of default routes in an orthogonal table."""
    table = [
        RoutingTableEntry({Routes.north}, 0x8, 0xf, {Routes.south}),  # Remove
        RoutingTableEntry({Routes.north}, 0x0, 0xf, {Routes.south}),  # Keep
        RoutingTableEntry({Routes.north}, 0x0, 0x8, {None}),  # Keep
    ]
    assert minimise(table, None) == table[1:]


def test_minimise_oversized():
    table = [
        RoutingTableEntry({Routes.north}, i, 0xf, {None}) for i in range(10)
    ]

    with pytest.raises(MinimisationFailedError) as exc:
        minimise(table, 5)
    assert "10" in str(exc.value)
    assert "5" in str(exc.value)


def test_is_defaultable_check_for_aliases():
    # A table with three entries, the first may be default routed. The second
    # could be default routable if not for aliasing the second entry.
    table = [
        RoutingTableEntry({Routes.north}, 0x1, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x8, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x8, 0xf, {Routes.east}),
    ]

    # The first entry should be defaultable regardless
    assert _is_defaultable(0, table[0], table, check_for_aliases=True) is True
    assert _is_defaultable(0, table[0], table, check_for_aliases=False) is True

    # The alias check should disallow removing the second entry since it
    # aliases the third entry.
    assert _is_defaultable(1, table[1], table, check_for_aliases=True) is False

    # But skipping the alias check should allow the second entry blindly
    assert _is_defaultable(1, table[1], table, check_for_aliases=False) is True


def test_minimise_check_for_aliases():
    # A table with three entries, the first may be default routed. The second
    # could be default routable if not for aliasing the second entry.
    table = [
        RoutingTableEntry({Routes.north}, 0x1, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x8, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x8, 0xf, {Routes.east}),
    ]

    # If alias checking is on (the default), only the first entry should be
    # removed.
    assert minimise(table, None) == table[1:]
    assert minimise(table, None, check_for_aliases=True) == table[1:]

    # If alias checking is off the first two entries should be removed (note
    # that the second entry being removed is actually incorrect but not spotted
    # when alias checking is disabled).
    assert minimise(table, None, check_for_aliases=False) == table[2:]


def test_minimise_same_mask(monkeypatch):
    # Wrap the _is_defaultable check to allow checking of calls.
    is_defaultable = Mock(side_effect=_is_defaultable)
    monkeypatch.setattr(remove_default_routes, "_is_defaultable",
                        is_defaultable)

    # If all masks are the same and no keys overlap should skip alias check
    table = [
        RoutingTableEntry({Routes.north}, 0x1, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x2, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x3, 0xf, {Routes.south}),
    ]
    assert minimise(table, None) == []
    for call in is_defaultable.mock_calls:
        assert call[1][3] is False
    is_defaultable.reset_mock()

    # If some masks differ, should do alias check.
    table = [
        RoutingTableEntry({Routes.north}, 0x1, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x2, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x3, 0xff, {Routes.south}),
    ]
    assert minimise(table, None) == []
    for call in is_defaultable.mock_calls:
        assert call[1][3] is True
    is_defaultable.reset_mock()

    # If some keys are repeated, should do alias check.
    table = [
        RoutingTableEntry({Routes.north}, 0x1, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x2, 0xf, {Routes.south}),
        RoutingTableEntry({Routes.north}, 0x1, 0xf, {Routes.south}),
    ]
    assert minimise(table, None) == [table[0]]
    for call in is_defaultable.mock_calls:
        assert call[1][3] is True
    is_defaultable.reset_mock()
