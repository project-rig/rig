from rig.links import Links


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


def test_links_opposite():
    assert Links.north.opposite == Links.south
    assert Links.north_east.opposite == Links.south_west
    assert Links.east.opposite == Links.west
    assert Links.south.opposite == Links.north
    assert Links.south_west.opposite == Links.north_east
    assert Links.west.opposite == Links.east
