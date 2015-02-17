"""Definitions of the resources available in a SpiNNaker machine.

Overview
--------

* :py:class:`~.rig.machine.Links` gives identifiers for links in a machine

* :py:class:`~.rig.machine.Cores`, :py:class:`~.rig.machine.SDRAM` and
  :py:class:`~.rig.machine.SDRAM` are (suggested) identifiers for common
  resources in a SpiNNaker machine.

* :py:class:`~.rig.machine.Machine` defines resources what resources are
  available in a machine.

"""

from enum import Enum, IntEnum

import sentinel


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


"""Resource identifier for (monitor and application) processor cores.

Note that this identifer does not trigger any kind of special-case behaviour in
library functions. Users are free to define their own alternatives.
"""
Cores = sentinel.create("Cores")


"""Resource identifier for shared off-die SDRAM (in bytes).

Note that this identifer does not trigger any kind of special-case behaviour in
library functions. Users are free to define their own alternatives.
"""
SDRAM = sentinel.create("SDRAM")


"""Resource identifier for shared on-die SRAM (in bytes).

Note that this identifer does not trigger any kind of special-case behaviour in
library functions. Users are free to define their own alternatives.
"""
SRAM = sentinel.create("SRAM")


class Machine(object):
    """Defines the resources available in a SpiNNaker machine.

    This datastructure makes the assumption that in most systems almost
    everything is uniform and working.

    This data-structure intends to be completely transparent. Its contents is
    described below. A number of utility methods are available but should be
    considered just that: utilities.

    Attributes
    ----------
    width : int
        The width of the system in chips: chips will thus have x-coordinates
        between 0 and width-1 inclusive.
    height : int
        The height of the system in chips: chips will thus have y-coordinates
        between 0 and height-1 inclusive.
    chip_resources : {resource_key: requirement, ...}
        The resources available on chips (unless otherwise stated in
        `chip_resource_exceptions). `resource_key` must be some unique
        identifying object for a given resource. `requirement` must be a
        positive numerical value.
    chip_resource_exceptions : {(x,y): resources, ...}
        If any chip's resources differ from those specified in
        `chip_resources`, an entry in this dictionary with the key being the
        chip's coordinates as a tuple `(x, y)` and `resources` being a
        dictionary of the same format as `chip_resources`. Note that every
        exception must specify exactly the same set of keys as
        `chip_resources`.
    dead_chips : set
        A set of `(x,y)` tuples enumerating all chips which completely
        unavailable. Links leaving a dead chip are implicitly marked as dead.
    dead_links : set
        A set `(x,y,link)` where `x` and `y` are a chip's coordinates and
        `link` is a value from the Enum :py:class:`~rig.machine.Links`. Note
        that links have two directions and both should be defined if a link is
        dead in both directions (the typical case).
    """
    __slots__ = ["width", "height", "chip_resources",
                 "chip_resource_exceptions", "dead_chips", "dead_links"]

    def __init__(self, width, height,
                 chip_resources={Cores: 18, SDRAM: 128*1024*1024,
                                 SRAM: 32*1024},
                 chip_resource_exceptions={}, dead_chips=set(),
                 dead_links=set()):
        """Defines the resources available within a SpiNNaker system.

        Parameters
        ----------
        width : int
        height : int
        chip_resources : {resource_key: requirement, ...}
        chip_resource_exceptions : {(x,y): resources, ...}
        dead_chips : set([(x,y,p), ...])
        dead_links : set([(x,y,link), ...])
        """
        self.width = width
        self.height = height

        self.chip_resources = chip_resources.copy()
        self.chip_resource_exceptions = chip_resource_exceptions.copy()

        self.dead_chips = dead_chips.copy()
        self.dead_links = dead_links.copy()

    def copy(self):
        """Produce a copy of this datastructure."""
        return Machine(
            self.width, self.height,
            self.chip_resources, self.chip_resource_exceptions,
            self.dead_chips, self.dead_links)

    def __contains__(self, chip_or_link):
        """Test if a given chip or link is present and alive.

        Parameter
        ---------
        chip_or_link : tuple
            If of the form `(x, y, link)`, checks a link. If of the form `(x,
            y)`, checks a core.
        """
        if len(chip_or_link) == 2:
            x, y = chip_or_link
            return 0 <= x < self.width and 0 <= y < self.height \
                and (x, y) not in self.dead_chips
        elif len(chip_or_link) == 3:
            x, y, link = chip_or_link
            return (x, y) in self and (x, y, link) not in self.dead_links
        else:
            raise ValueError("Expect either (x, y) or (x, y, link).")

    def __getitem__(self, xy):
        """Get the resources available to a given chip.

        Raises
        ------
        IndexError
            If the given chip is dead or not within the bounds of the system.
        """
        if xy not in self:
            raise IndexError("{} is not part of the machine.".format(repr(xy)))

        return self.chip_resource_exceptions.get(xy, self.chip_resources)

    def __setitem__(self, xy, resources):
        """Specify the resources available to a given chip.

        Raises
        ------
        IndexError
            If the given chip is dead or not within the bounds of the system.
        """
        if xy not in self:
            raise IndexError("{} is not part of the machine.".format(repr(xy)))

        self.chip_resource_exceptions[xy] = resources
