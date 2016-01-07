import pytest

from rig.routing_table import (Routes, RoutingTableEntry,
                               MinimisationFailedError)
from rig.routing_table.remove_default_routes import minimise


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
