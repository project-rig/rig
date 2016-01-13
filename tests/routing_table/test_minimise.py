from rig.routing_table import (
    minimise_tables, minimise_table, Routes, MinimisationFailedError)
from rig.routing_table import RoutingTableEntry as RTE
import pytest


def test_minimise_table():
    """Test minimisation of a single routing table."""
    # First method achieves sufficient minimisation
    table = [RTE({Routes.north}, i, 0xf, {Routes.south}) for i in range(10)]
    assert minimise_table(table, 5) == list()

    # Last method achieves sufficient minimisation (custom method)
    def minimiser1(table, target_length):
        raise MinimisationFailedError(target_length, target_length)

    def minimiser2(table, target_length):
        return list()

    assert minimise_table(table, 5, methods=(minimiser1, minimiser2)) == list()

    # Insufficient minimisation
    def minimiser1(table, target_length):
        raise MinimisationFailedError(target_length, target_length + 5)

    def minimiser2(table, target_length):
        raise MinimisationFailedError(target_length, target_length + 10)

    with pytest.raises(MinimisationFailedError) as exc:
        minimise_table(table, 5, methods=(minimiser1, minimiser2))

    assert exc.value.final_length == 10

    # If there are no methods and the table is sufficiently small then we
    # should just get the table back.
    table = [RTE({Routes.north}, i, 0xf, {Routes.south}) for i in range(10)]
    assert minimise_table(table, 1024, methods=list()) == table

    # If there are no methods and the table is NOT sufficiently small then an
    # error should be raised
    table = [RTE({Routes.north}, i, 0xf, {Routes.south}) for i in range(10)]
    with pytest.raises(MinimisationFailedError):
        minimise_table(table, 1, methods=list())


def test_minimise_table_smallest_possible():
    """Test minimising a table using the method which results in the smallest
    table.
    """
    # Removing default entries will achieve the best result
    table = [
        RTE({Routes.south}, 0x0, 0xf, {Routes.north}),
        RTE({Routes.north}, 0x1, 0xf, {Routes.south}),
    ]
    assert len(minimise_table(table, None)) == 0

    # Ordered covering will achieve the best result
    table = [
        RTE({Routes.east}, 0x0, 0xf, {Routes.north}),
        RTE({Routes.east}, 0x1, 0xf, {Routes.south}),
    ]
    assert minimise_table(table, None) == [
        RTE({Routes.east}, 0x0, 0xe, {Routes.north, Routes.south})
    ]


def test_minimise_smallest_possible():
    """Test minimising a table using the method which results in the smallest
    table.
    """
    # Removing default entries will achieve the best result
    table = [
        RTE({Routes.south}, 0x0, 0xf, {Routes.north}),
        RTE({Routes.north}, 0x1, 0xf, {Routes.south}),
    ]
    assert minimise_tables({(0, 0): table}, None) == dict()

    # Ordered covering will achieve the best result
    table = [
        RTE({Routes.east}, 0x0, 0xf, {Routes.north}),
        RTE({Routes.east}, 0x1, 0xf, {Routes.south}),
    ]
    assert minimise_tables({(1, 1): table}, None) == {
        (1, 1): [RTE({Routes.east}, 0x0, 0xe, {Routes.north, Routes.south})]
    }


def test_minimise_tables():
    """Test minimising several tables using multiple algorithms and specified
    lengths.
    """
    # Create the tables
    tables = {
        (0, 0): [RTE({Routes.south}, 0x0, 0xf, {Routes.west}),
                 RTE({Routes.north}, 0x1, 0xf, {Routes.west})],
        (0, 1): [RTE({Routes.south}, 0x0, 0xf, {Routes.west}),
                 RTE({Routes.north}, 0x1, 0xf, {Routes.west}),
                 RTE({Routes.north}, 0x2, 0xf, {Routes.west})],
    }

    # Set the table lengths
    lengths = {(0, 0): 2, (0, 1): 0}

    # Minimise the tables; ensure that the error that is raised refers to
    # chip (0, 1)
    with pytest.raises(MinimisationFailedError) as exc:
        minimise_tables(tables, lengths)

    assert exc.value.chip == (0, 1)
