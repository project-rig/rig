import pytest

from rig.machine import Machine, Links, Cores, SDRAM, SRAM


class TestMachine(object):
    def test_constructor_copies(self):
        """Test that arguments are coped"""
        width = 8
        height = 12

        chip_resources = {Cores: 1, SDRAM: 321, SRAM: 123}
        chip_resource_exceptions = {(0, 0): {Cores: 0, SDRAM: 321, SRAM: 5}}

        dead_chips = set([(1, 1)])
        dead_links = set([(0, 0, Links.south_west),
                          (width-1, height-1, Links.north_east)])

        machine = Machine(width, height, chip_resources,
                          chip_resource_exceptions, dead_chips, dead_links)

        assert machine.width == width
        assert machine.height == height

        assert machine.chip_resources == chip_resources
        assert machine.chip_resources is not chip_resources
        assert machine.chip_resource_exceptions == chip_resource_exceptions
        assert machine.chip_resource_exceptions is not chip_resource_exceptions

        assert machine.dead_chips == dead_chips
        assert machine.dead_chips is not dead_chips
        assert machine.dead_links == dead_links
        assert machine.dead_links is not dead_links

    def test_copy(self):
        """Test copy function works correctly"""
        width = 8
        height = 12

        chip_resources = {Cores: 1, SDRAM: 321, SRAM: 123}
        chip_resource_exceptions = {(0, 0): {Cores: 0, SDRAM: 321, SRAM: 5}}

        dead_chips = set([(1, 1)])
        dead_links = set([(0, 0, Links.south_west),
                          (width-1, height-1, Links.north_east)])

        machine = Machine(width, height, chip_resources,
                          chip_resource_exceptions, dead_chips, dead_links)

        other_machine = machine.copy()

        assert machine.width == other_machine.width
        assert machine.height == other_machine.height

        assert machine.chip_resources == other_machine.chip_resources
        assert machine.chip_resources is not other_machine.chip_resources
        assert machine.chip_resource_exceptions \
            == other_machine.chip_resource_exceptions
        assert machine.chip_resource_exceptions \
            is not other_machine.chip_resource_exceptions

        assert machine.dead_chips == other_machine.dead_chips
        assert machine.dead_chips is not other_machine.dead_chips
        assert machine.dead_links == other_machine.dead_links
        assert machine.dead_links is not other_machine.dead_links

    def test_in(self):
        """Ensure membership tests work."""
        width = 10
        height = 10

        # Hard-coded dead elements
        dead_chips = set([(1, 1)])
        dead_links = set([(0, 0, Links.south_west)])

        machine = Machine(width, height,
                          dead_chips=dead_chips, dead_links=dead_links)

        # Some sort of error when we test something insane
        with pytest.raises(ValueError):
            (1, 2, 3, 4) in machine

        # Exhaustive check of chip membership
        for x in range(width):
            for y in range(height):
                if (x, y) != (1, 1):
                    assert (x, y) in machine
                    for link in Links:
                        if (x, y, link) != (0, 0, Links.south_west):
                            assert (x, y, link) in machine
                        else:
                            assert (x, y, link) not in machine
                else:
                    assert (x, y) not in machine
                    for link in Links:
                        assert (x, y, link) not in machine

        # Check membership outside machine's bounds
        for x, y in ((0, -1), (-1, 0), (-1, -1),
                     (width, 0), (0, height), (width, height)):
            assert (x, y) not in machine
            for link in Links:
                assert (x, y, link) not in machine

    def test_resource_lookup(self):
        """Check can get/set resources for specified chips."""
        width = 2
        height = 2

        chip_resources = {Cores: 1, SDRAM: 2, SRAM: 3}
        chip_resource_exceptions = {(0, 0): {Cores: 4, SDRAM: 5, SRAM: 6}}

        machine = Machine(width, height, chip_resources,
                          chip_resource_exceptions)

        # Exhaustive lookup test
        for x in range(width):
            for y in range(width):
                if (x, y) != (0, 0):
                    assert machine[(x, y)] == chip_resources
                else:
                    assert machine[(x, y)] == chip_resource_exceptions[(0, 0)]

        # Test setting
        new_resource_exception = {Cores: 7, SDRAM: 8, SRAM: 9}
        machine[(1, 1)] = new_resource_exception
        assert machine[(1, 1)] == new_resource_exception

        # Test with non-existing chips
        with pytest.raises(IndexError):
            machine[(-1, -1)]
        with pytest.raises(IndexError):
            machine[(-1, -1)] = new_resource_exception


def test_links_from_vector():
    # In all but the last of the following tests we assume we're in a 4x8
    # system.

    # Direct neighbours without wrapping
    assert Links.from_vector((+1, +0)) == Links.east
    assert Links.from_vector((-1, -0)) == Links.west
    assert Links.from_vector((+0, +1)) == Links.north
    assert Links.from_vector((-0, -1)) == Links.south
    assert Links.from_vector((+1, +1)) == Links.north_east
    assert Links.from_vector((-1, -1)) == Links.south_west

    # Direct neighbours with wrapping on X
    assert Links.from_vector((-3, -0)) == Links.east
    assert Links.from_vector((+3, +0)) == Links.west

    # Direct neighbours with wrapping on Y
    assert Links.from_vector((-0, -7)) == Links.north
    assert Links.from_vector((+0, +7)) == Links.south

    # Direct neighbours with wrapping on X & Y
    assert Links.from_vector((-3, +1)) == Links.north_east
    assert Links.from_vector((+3, -1)) == Links.south_west

    assert Links.from_vector((+1, -7)) == Links.north_east
    assert Links.from_vector((-1, +7)) == Links.south_west

    assert Links.from_vector((-3, -7)) == Links.north_east
    assert Links.from_vector((+3, +7)) == Links.south_west

    # Special case: 2xN or Nx2 system (N >= 2) "spiraing" around the Z axis
    assert Links.from_vector((1, -1)) == Links.south_west
    assert Links.from_vector((-1, 1)) == Links.north_east


def test_links_to_vector():
    assert (+1, +0) == Links.east.to_vector()
    assert (-1, -0) == Links.west.to_vector()
    assert (+0, +1) == Links.north.to_vector()
    assert (-0, -1) == Links.south.to_vector()
    assert (+1, +1) == Links.north_east.to_vector()
    assert (-1, -1) == Links.south_west.to_vector()


def test_has_wrap_around_links():
    # Test singleton with wrap-arounds
    machine = Machine(1, 1)
    assert machine.has_wrap_around_links()
    assert machine.has_wrap_around_links(1.0)
    assert machine.has_wrap_around_links(0.1)

    # Test singleton with dead chip
    machine = Machine(1, 1, dead_chips=set([(0, 0)]))
    assert not machine.has_wrap_around_links()
    assert not machine.has_wrap_around_links(1.0)
    assert not machine.has_wrap_around_links(0.1)

    # Test singleton with one dead link
    machine = Machine(1, 1, dead_links=set([(0, 0, Links.north)]))
    assert machine.has_wrap_around_links(5.0 / 6.0)
    assert not machine.has_wrap_around_links(1.0)

    # Test fully-working larger machine
    machine = Machine(10, 10)
    assert machine.has_wrap_around_links()
    assert machine.has_wrap_around_links(1.0)
    assert machine.has_wrap_around_links(0.1)

    # Test larger machine with 50% dead links (note that we simply kill 50% of
    # links on border chips, not all chips, ensuring this function probably
    # isn't testing all links, just those on the borders)
    machine = Machine(10, 10, dead_links=set(
        [(x, y, link)
         for x in range(10)
         for y in range(10)
         for link in [Links.north, Links.west, Links.south_west]
         if x == 0 or y == 0]))
    assert not machine.has_wrap_around_links(1.0)
    assert machine.has_wrap_around_links(0.5)
    assert machine.has_wrap_around_links(0.1)
