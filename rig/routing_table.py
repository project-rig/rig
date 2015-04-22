"""Data structures for the definition of SpiNNaker routing tables.
"""

from enum import IntEnum

from rig.utils.docstrings import add_int_enums_to_docstring

from collections import namedtuple


class RoutingTableEntry(namedtuple("RoutingTableEntry", "route key mask")):
    """Named tuple representing a single routing entry in a SpiNNaker routing
    table.

    Parameters
    ----------
    route : set([Routes, ...])
        The set of destinations a packet should be routed to where each element
        in the set is a value from the enumeration
        :py:class:`~rig.routing_table.Routes`.
    key : int
        32-bit unsigned integer routing key to match after applying the mask.
    mask : int
        32-bit unsigned integer mask to apply to keys of packets arriving at
        the router.
    """


@add_int_enums_to_docstring
class Routes(IntEnum):
    """Enumeration of routes which a SpiNNaker packet can take after arriving
    at a router.

    Note that the integer values assigned are chosen to match the numbers used
    to identify routes in the low-level software API and hardware registers.

    Note that you can directly cast from a :py:class:`rig.machine.Links` to a
    Routes value.
    """

    @classmethod
    def core(cls, num):
        """Get the :py:class:`.Routes` for the numbered core."""
        assert 0 <= num <= 17, "Cores are numbered from 0 to 17"
        return cls(6 + num)

    east = 0
    north_east = 1
    north = 2
    west = 3
    south_west = 4
    south = 5

    core_monitor = 6
    core_1 = 7
    core_2 = 8
    core_3 = 9
    core_4 = 10
    core_5 = 11
    core_6 = 12
    core_7 = 13
    core_8 = 14
    core_9 = 15
    core_10 = 16
    core_11 = 17
    core_12 = 18
    core_13 = 19
    core_14 = 20
    core_15 = 21
    core_16 = 22
    core_17 = 23
