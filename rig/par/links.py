"""Unique identifiers for links in a SpiNNaker system.
"""

from enum import Enum, IntEnum


class Links(IntEnum):
    """Enumeration of links from a SpiNNaker chip.

    Note that the numbers chosen have two useful properties:
    * The integer values assigned are chosen to match the numbers used to
      identify the links in the low-level software API and hardware registers.
    * The links are ordered consecutively in anticlockwise order meaning the
      opposite link is `(link+3)%6`.
    """

    east = 0
    north_east = 1
    north = 2
    west = 3
    south_west = 4
    south = 5
