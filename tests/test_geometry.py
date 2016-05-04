import pytest

from rig.links import Links

from rig.geometry import concentric_hexagons, to_xyz, minimise_xyz, \
    shortest_mesh_path_length, shortest_mesh_path, \
    shortest_torus_path_length, shortest_torus_path, \
    standard_system_dimensions, spinn5_eth_coords, spinn5_local_eth_coord, \
    spinn5_chip_coord, spinn5_fpga_link


def test_concentric_hexagons():
    # Zero layers should just give a singleton
    assert set(concentric_hexagons(0)) == set([(0, 0)])
    assert set(concentric_hexagons(0, (3, 2))) == set([(3, 2)])

    # Test single layers exhaustively
    assert set(concentric_hexagons(1)) \
        == set([(0, 0),
                (+1, 0), (-1, 0),     # Left and right
                (0, +1), (0, -1),     # Above and below
                (+1, +1), (-1, -1)])  # "Diagnoally"

    assert set(concentric_hexagons(1, (10, 100))) \
        == set([(10, 100),
                (11, 100), (9, 100),  # Left and right
                (10, 101), (10, 99),  # Above and below
                (11, 101), (9, 99)])  # "Diagnoally"

    # Test larger number of layers analytically
    num_layers = 10
    hexagons = set(concentric_hexagons(num_layers))

    # Check total number of hexagons:
    total_hexagons = 3 * num_layers * (num_layers + 1) + 1
    assert len(hexagons) == total_hexagons

    # Check that only the outer hexagons are not fully surrounded
    outer_hexagons = set()
    inner_hexagons = set()
    for x, y in hexagons:
        # Layer number calculated according to
        # http://jhnet.co.uk/articles/torus_paths
        m = sorted((x, y, 0))[1]
        layer = abs(x-m) + abs(y-m) + abs(-m)

        if set([(x, y),
                (x + 1, y), (x - 1, y),
                (x, y + 1), (x, y - 1),
                (x + 1, y + 1), (x - 1, y - 1)]).issubset(hexagons):
            inner_hexagons.add((x, y))
            # Hexagons which are fully surrounded must not be on the outer
            # layer.
            assert layer < num_layers
        else:
            outer_hexagons.add((x, y))
            # Hexagons which are not fully surrounded must be on the outer
            # layer.
            assert layer == num_layers

    # Check there are the correct number of hexagons in each layer (though this
    # is strictly unnecessary given the above test, but who tests the tests?)
    assert len(outer_hexagons) == 6 * num_layers
    assert len(inner_hexagons) == total_hexagons - (6 * num_layers)


def test_to_xyz():
    # Test with combinations of positive/negative/zero values.
    assert to_xyz((0, 0)) == (0, 0, 0)
    assert to_xyz((1, 0)) == (1, 0, 0)
    assert to_xyz((0, 1)) == (0, 1, 0)
    assert to_xyz((1, 1)) == (1, 1, 0)
    assert to_xyz((-1, 0)) == (-1, 0, 0)
    assert to_xyz((-1, 1)) == (-1, 1, 0)
    assert to_xyz((0, -1)) == (0, -1, 0)
    assert to_xyz((1, -1)) == (1, -1, 0)
    assert to_xyz((-1, -1)) == (-1, -1, 0)


# A series of hexagonal vectors along with their (mesh) minimal counterparts
# for testing hexagonal coordinate minimisation-related functions
test_mesh_vectors = [
    # Already-minimal examples
    ((0, 0, 0), (0, 0, 0)),

    ((1, 0, 0), (1, 0, 0)),
    ((0, 1, 0), (0, 1, 0)),
    ((0, 0, 1), (0, 0, 1)),

    ((-1, 0, 0), (-1, 0, 0)),
    ((0, -1, 0), (0, -1, 0)),
    ((0, 0, -1), (0, 0, -1)),

    ((1, -1, 0), (1, -1, 0)),
    ((0, 1, -1), (0, 1, -1)),
    ((-1, 0, 1), (-1, 0, 1)),
    ((0, -1, 1), (0, -1, 1)),

    # Minimise (+x, +y, 0) and (-x, -y, 0)
    ((1, 1, 0), (0, 0, -1)),
    ((-1, -1, 0), (0, 0, 1)),
    ((2, 1, 0), (1, 0, -1)),
    ((-2, -1, 0), (-1, 0, 1)),

    # Minimise (+x, 0, +z) and (-x, 0, -z)
    ((1, 0, 1), (0, -1, 0)),
    ((-1, 0, -1), (0, 1, 0)),
    ((2, 0, 1), (1, -1, 0)),
    ((-2, 0, -1), (-1, 1, 0)),

    # Minimise (0, +y, +z) and (0, -y, -z)
    ((0, 1, 1), (-1, 0, 0)),
    ((0, -1, -1), (1, 0, 0)),
    ((0, 2, 1), (-1, 1, 0)),
    ((0, -2, -1), (1, -1, 0)),

    # Minimise with all three elements set
    ((1, 1, 1), (0, 0, 0)),
    ((1, 2, 3), (-1, 0, 1)),
    ((-1, -2, -3), (1, 0, -1)),

    # Minimise with all three elements set with mixed signs
    ((-1, -2, 3), (0, -1, 4)),
    ((-1, 2, -3), (0, 3, -2)),
    ((1, -2, -3), (3, 0, -1)),
]


def test_minimise_xyz():
    for vector, minimised in test_mesh_vectors:
        assert minimise_xyz((vector)) == minimised, (vector, minimised)


def test_shortest_mesh_path_length():
    # Test magnitude calculation when starting from a range of starting offsets
    for offset in [(0, 0, 0),     # Origin
                   (1, 2, 3),     # All Positive
                   (-1, -2, -3),  # All Negative
                   (-1, 2, -3)]:  # Mixed
        for end, minimised in test_mesh_vectors:
            start = offset
            end = tuple(e + o for e, o in zip(end, offset))
            magnitude = sum(map(abs, minimised))
            assert shortest_mesh_path_length(start, end) == magnitude, \
                (start, end, magnitude)
            assert shortest_mesh_path_length(end, start) == magnitude, \
                (end, start, magnitude)


def test_shortest_mesh_path():
    # Test paths starting from a range of starting offsets
    for offset in [(0, 0, 0),     # Origin
                   (1, 2, 3),     # All Positive
                   (-1, -2, -3),  # All Negative
                   (-1, 2, -3)]:  # Mixed
        for end, minimised in test_mesh_vectors:
            start = offset
            end = tuple(e + o for e, o in zip(end, offset))
            neg_minimised = tuple(-m for m in minimised)
            assert shortest_mesh_path(start, end) == minimised, \
                (start, end, minimised)
            assert shortest_mesh_path(end, start) == neg_minimised, \
                (end, start, neg_minimised)

# A series of hexagonal vectors along with their possibly multiple (torus)
# minimal counterparts in the specified torus size for testing hexagonal
# coordinate minimisation-related functions.
# [((dx, dy, dz), set([(dx, dy, dz), ...]), (width, height)), ...]
test_torus_vectors = [
    # Non-wrapping, already-minimal examples
    ((0, 0, 0), set([(0, 0, 0)]), (10, 10)),

    ((1, 0, 0), set([(1, 0, 0)]), (10, 10)),
    ((0, 1, 0), set([(0, 1, 0)]), (10, 10)),
    ((0, 0, 1), set([(0, 0, 1)]), (10, 10)),

    # Two-element, non-minimal, non-wrapping examples
    ((1, 1, 0), set([(0, 0, -1)]), (10, 10)),
    ((-1, 0, -1), set([(0, 1, 0)]), (10, 10)),
    ((0, -1, -1), set([(1, 0, 0)]), (10, 10)),

    # Two-element, already-minimal wrapping on each axis
    ((4, 0, 0), set([(-1, 0, 0)]), (5, 10)),  # X
    ((0, 9, 0), set([(0, -1, 0)]), (5, 10)),  # Y
    ((0, 0, 1), set([(0, 0, 1)]), (5, 10)),   # Both
    ((0, 0, 9), set([(0, 0, -1)]), (5, 10)),  # Both (twice on Y)

    # Non-minimal examples of wrapping on each axis
    ((5, 1, 1), set([(-1, 0, 0)]), (5, 10)),    # +(1, 1, 1) X
    ((1, 10, 1), set([(0, -1, 0)]), (5, 10)),   # +(1, 1, 1) Y
    ((1, 1, 2), set([(0, 0, 1)]), (5, 10)),     # +(1, 1, 1) Both
    ((1, 1, 10), set([(0, 0, -1)]), (5, 10)),   # +(1, 1, 1) Both (twice on Y)
    ((3, -1, -1), set([(-1, 0, 0)]), (5, 10)),  # -(1, 1, 1) X
    ((-1, 8, -1), set([(0, -1, 0)]), (5, 10)),  # -(1, 1, 1) Y
    ((-1, -1, 0), set([(0, 0, 1)]), (5, 10)),   # -(1, 1, 1) Both
    ((-1, -1, 8), set([(0, 0, -1)]), (5, 10)),  # -(1, 1, 1) Both (twice on Y)

    # Around bottom left corner
    ((0, 0, 0), set([(0, 0, 0)]), (8, 16)),
    ((1, 0, 0), set([(1, 0, 0)]), (8, 16)),
    ((0, 1, 0), set([(0, 1, 0)]), (8, 16)),
    ((0, 0, -1), set([(0, 0, -1)]), (8, 16)),
    ((1, 1, 0), set([(0, 0, -1)]), (8, 16)),

    # Around bottom right corner
    ((7, 0, 0), set([(-1, 0, 0)]), (8, 16)),
    ((6, 0, 0), set([(-2, 0, 0)]), (8, 16)),
    ((7, 1, 0), set([(-1, 1, 0)]), (8, 16)),
    ((6, 1, 0), set([(-2, 1, 0)]), (8, 16)),

    # Around top left corner
    ((0, 15, 0), set([(0, -1, 0)]), (8, 16)),
    ((1, 15, 0), set([(1, -1, 0)]), (8, 16)),
    ((0, 14, 0), set([(0, -2, 0)]), (8, 16)),
    ((1, 14, 0), set([(1, -2, 0)]), (8, 16)),

    # Around top right corner
    ((7, 15, 0), set([(0, 0, 1)]), (8, 16)),
    ((6, 15, 0), set([(-1, 0, 1)]), (8, 16)),
    ((7, 14, 0), set([(0, -1, 1)]), (8, 16)),
    ((7, 15, 1), set([(0, 0, 2)]), (8, 16)),
    ((6, 14, 0), set([(0, 0, 2)]), (8, 16)),

    # Ambiguous: Direct or wrap X
    ((2, 0, 0), set([(2, 0, 0), (-2, 0, 0)]), (4, 4)),

    # Ambiguous: Direct or wrap Y
    ((0, 2, 0), set([(0, 2, 0), (0, -2, 0)]), (4, 4)),

    # Ambiguous: Direct or wrap X & Y
    ((2, 2, 0), set([(0, 0, -2), (0, 0, 2)]), (4, 4)),

    # Ambiguous: Direct, wrap X or lots of wraps Y (via "diagonal")
    ((4, 0, 0), set([(4, 0, 0), (2, 0, -2), (0, 0, -4)]), (16, 2)),
    ((12, 0, 0), set([(-4, 0, 0), (-2, 0, 2), (0, 0, 4)]), (16, 2)),

    # Ambiguous: Direct, wrap Y or lots of wraps X (via "diagonal")
    ((0, 4, 0), set([(0, 4, 0), (0, 2, -2), (0, 0, -4)]), (2, 16)),
    ((0, 12, 0), set([(0, -4, 0), (0, -2, 2), (0, 0, 4)]), (2, 16)),

    # Ambiguous: Direct, wrap X or wraps Y (via "diagonal")
    ((2, 0, 0), set([(-1, 0, 0), (0, 0, 1)]), (3, 1)),

    # Ambiguous: Direct or wrap Y (via "diagonal")
    ((2, 0, 0), set([(2, 0, 0), (0, 0, -2)]), (8, 2)),

    # Ambiguous: Direct or wrap Y (via "diagonal")
    ((1, 0, 0), set([(1, 0, 0), (0, 0, -1)]), (3, 1)),

    # Ambiguous: Direct, wrap X, wrap Y (via "diagonal") or wrap X & Y (via
    # "diagonal")
    ((1, 0, 0), set([(1, 0, 0), (-1, 0, 0), (0, 0, -1), (0, 0, 1)]), (2, 1)),

    # Ambiguous: Many possible wraps
    ((5, 0, 0), set([(5, 0, 0), (3, 0, -2), (1, 0, -4)]), (20, 2)),
    ((0, 5, 0), set([(0, 5, 0), (0, 3, -2), (0, 1, -4)]), (2, 20)),
]


def test_shortest_torus_path_length():
    # Test magnitude calculation when starting from a range of starting offsets
    for offset in [(0, 0, 0),     # Origin
                   (1, 2, 3),     # All Positive
                   (-1, -2, -3),  # All Negative
                   (-1, 2, -3)]:  # Mixed
        for end, minimiseds, (width, height) in test_torus_vectors:
            start = offset
            end = tuple(e + o for e, o in zip(end, offset))
            magnitude = sum(map(abs, next(iter(minimiseds))))
            assert shortest_torus_path_length(start, end, width, height) \
                == magnitude, \
                (start, end, width, height, magnitude)
            assert shortest_torus_path_length(end, start, width, height) \
                == magnitude, \
                (end, start, width, height, magnitude)


def test_shortest_torus_path():
    # Test paths starting from a range of starting offsets
    for offset in [(0, 0, 0),     # Origin
                   (1, 2, 3),     # All Positive
                   (-1, -2, -3),  # All Negative
                   (-1, 2, -3)]:  # Mixed
        for end, minimiseds, (width, height) in test_torus_vectors:
            start = offset
            end = tuple(e + o for e, o in zip(end, offset))

            unseen_minimiseds = minimiseds.copy()

            neg_minimiseds = set(tuple(-m for m in minimised)
                                 for minimised in minimiseds)
            unseen_neg_minimiseds = neg_minimiseds.copy()

            # In cases where multiple solutions exist, make sure we see all of
            # them given a large number of tests. Note that the chances of this
            # test failing for a working implementation should be incredibly
            # low.
            for _ in range(1000):  # pragma: no branch
                path = shortest_torus_path(start, end, width, height)
                assert path in minimiseds, \
                    (start, end, width, height, minimiseds)
                try:
                    unseen_minimiseds.remove(path)
                except KeyError:
                    pass
            assert unseen_minimiseds == set(), \
                (start, end, width, height, minimiseds)

            for _ in range(1000):  # pragma: no branch
                path = shortest_torus_path(end, start, width, height)
                assert path in neg_minimiseds, \
                    (end, start, width, height, neg_minimiseds)
                try:
                    unseen_neg_minimiseds.remove(path)
                except KeyError:
                    pass
            assert unseen_neg_minimiseds == set(), \
                (start, end, width, height, neg_minimiseds)


def test_standard_system_dimensions():
    # Special case: 0
    assert standard_system_dimensions(0) == (0, 0)

    # Special case: 1
    assert standard_system_dimensions(1) == (8, 8)

    # Should crash on non-multiples of 3
    with pytest.raises(ValueError):
        standard_system_dimensions(2)
    with pytest.raises(ValueError):
        standard_system_dimensions(5)

    # Square systems
    assert standard_system_dimensions(3 * 1 * 1) == (12, 12)
    assert standard_system_dimensions(3 * 2 * 2) == (24, 24)
    assert standard_system_dimensions(3 * 20 * 20) == (240, 240)

    # Rectangular systems (should always be wide)
    assert standard_system_dimensions(3 * 1 * 2) == (24, 12)
    assert standard_system_dimensions(3 * 1 * 3) == (36, 12)
    assert standard_system_dimensions(3 * 2 * 4) == (48, 24)
    assert standard_system_dimensions(3 * 1 * 17) == (204, 12)


def test_spinn5_eth_coords():
    # Minimal system
    assert set(spinn5_eth_coords(12, 12)) == set([(0, 0), (4, 8), (8, 4)])

    # Larger, non-square systems
    assert set(spinn5_eth_coords(24, 12)) == set([
        (0, 0), (4, 8), (8, 4), (12, 0), (16, 8), (20, 4)])
    assert set(spinn5_eth_coords(12, 24)) == set([
        (0, 0), (4, 8), (8, 4), (0, 12), (4, 20), (8, 16)])

    # Larger square system
    assert set(spinn5_eth_coords(24, 24)) == set([
        (0, 0), (4, 8), (8, 4),
        (12, 0), (16, 8), (20, 4),
        (0, 12), (4, 20), (8, 16),
        (12, 12), (16, 20), (20, 16)
    ])

    # Subsets for non multiples of 12 (i.e. non-spinn-5 based things)
    assert set(spinn5_eth_coords(2, 2)) == set([(0, 0)])
    assert set(spinn5_eth_coords(8, 8)) == set([(0, 0)])

    # Machines with no 0, 0
    assert set(spinn5_eth_coords(12, 8, 4, 0)) == set([(0, 4), (4, 0)])
    assert set(spinn5_eth_coords(12, 8, 0, 4)) == set([(0, 4), (4, 0)])


def test_spinn5_local_eth_coord():
    # Points lie on actual eth chips
    assert spinn5_local_eth_coord(0, 0, 12, 12) == (0, 0)
    assert spinn5_local_eth_coord(4, 8, 12, 12) == (4, 8)
    assert spinn5_local_eth_coord(8, 4, 12, 12) == (8, 4)

    assert spinn5_local_eth_coord(12, 0, 24, 12) == (12, 0)
    assert spinn5_local_eth_coord(16, 8, 24, 12) == (16, 8)
    assert spinn5_local_eth_coord(20, 4, 24, 12) == (20, 4)

    assert spinn5_local_eth_coord(0, 12, 12, 24) == (0, 12)
    assert spinn5_local_eth_coord(8, 16, 12, 24) == (8, 16)
    assert spinn5_local_eth_coord(4, 20, 12, 24) == (4, 20)

    assert spinn5_local_eth_coord(12, 12, 24, 24) == (12, 12)
    assert spinn5_local_eth_coord(16, 20, 24, 24) == (16, 20)
    assert spinn5_local_eth_coord(20, 16, 24, 24) == (20, 16)

    # Exhaustive check for a 12x12 system
    cases = [
        # X:   0         1         2         3         4         5         6         7         8         9        10        11     # noqa Y:
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8)],  # noqa  0
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8)],  # noqa  1
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8)],  # noqa  2
        [(+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+4, +8), (+4, +8), (+4, +8), (+4, +8)],  # noqa  3
        [(+8, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  4
        [(+8, +4), (+8, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  5
        [(+8, +4), (+8, +4), (+8, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  6
        [(+8, +4), (+8, +4), (+8, +4), (+8, +4), (+0, +0), (+0, +0), (+0, +0), (+0, +0), (+8, +4), (+8, +4), (+8, +4), (+8, +4)],  # noqa  7
        [(+8, +4), (+8, +4), (+8, +4), (+8, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+8, +4), (+8, +4), (+8, +4)],  # noqa  8
        [(+8, +4), (+8, +4), (+8, +4), (+8, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+8, +4), (+8, +4)],  # noqa  9
        [(+8, +4), (+8, +4), (+8, +4), (+8, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+8, +4)],  # noqa 10
        [(+8, +4), (+8, +4), (+8, +4), (+8, +4), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8), (+4, +8)]   # noqa 11
    ]
    for y, row in enumerate(cases):
        for x, eth_coord in enumerate(row):
            assert spinn5_local_eth_coord(x, y, 12, 12) == eth_coord

    # Still works for non multiples of 12
    assert spinn5_local_eth_coord(0, 0, 2, 2) == (0, 0)
    assert spinn5_local_eth_coord(0, 1, 2, 2) == (0, 0)
    assert spinn5_local_eth_coord(1, 0, 2, 2) == (0, 0)
    assert spinn5_local_eth_coord(1, 1, 2, 2) == (0, 0)

    # Still works for machines with no (0, 0)
    assert spinn5_local_eth_coord(4, 0, 12, 8, 4, 0) == (4, 0)
    assert spinn5_local_eth_coord(4, 1, 12, 8, 4, 0) == (4, 0)
    assert spinn5_local_eth_coord(5, 0, 12, 8, 4, 0) == (4, 0)
    assert spinn5_local_eth_coord(5, 1, 12, 8, 4, 0) == (4, 0)

    assert spinn5_local_eth_coord(0, 4, 12, 8, 4, 0) == (0, 4)
    assert spinn5_local_eth_coord(0, 5, 12, 8, 4, 0) == (0, 4)
    assert spinn5_local_eth_coord(1, 4, 12, 8, 4, 0) == (0, 4)
    assert spinn5_local_eth_coord(1, 5, 12, 8, 4, 0) == (0, 4)

    # Types are normal Python integers
    x, y = spinn5_local_eth_coord(1, 1, 12, 12)
    assert isinstance(x, int)
    assert isinstance(y, int)


@pytest.mark.parametrize("dx", [0, 12, 24, 36])
@pytest.mark.parametrize("dy", [0, 12, 24, 36])
def test_spinn5_chip_coord(dx, dy):
    # Should work within a board
    assert spinn5_chip_coord(0 + dx, 0 + dy) == (0, 0)
    assert spinn5_chip_coord(4 + dx, 0 + dy) == (4, 0)
    assert spinn5_chip_coord(0 + dx, 3 + dy) == (0, 3)
    assert spinn5_chip_coord(7 + dx, 3 + dy) == (7, 3)
    assert spinn5_chip_coord(4 + dx, 7 + dy) == (4, 7)
    assert spinn5_chip_coord(7 + dx, 7 + dy) == (7, 7)
    assert spinn5_chip_coord(4 + dx, 4 + dy) == (4, 4)

    # Should work when wrapping around
    assert spinn5_chip_coord(5 + dx, 0 + dy) == (1, 4)
    assert spinn5_chip_coord(8 + dx, 3 + dy) == (4, 7)
    assert spinn5_chip_coord(8 + dx, 4 + dy) == (0, 0)
    assert spinn5_chip_coord(8 + dx, 7 + dy) == (0, 3)
    assert spinn5_chip_coord(8 + dx, 8 + dy) == (4, 0)
    assert spinn5_chip_coord(4 + dx, 8 + dy) == (0, 0)
    assert spinn5_chip_coord(3 + dx, 7 + dy) == (7, 3)
    assert spinn5_chip_coord(0 + dx, 4 + dy) == (4, 0)

    # Should work for machines without (0, 0)
    assert spinn5_chip_coord(4 + dx, 0 + dy, 4, 0) == (0, 0)
    assert spinn5_chip_coord(4 + dx, 1 + dy, 4, 0) == (0, 1)
    assert spinn5_chip_coord(5 + dx, 0 + dy, 4, 0) == (1, 0)
    assert spinn5_chip_coord(5 + dx, 1 + dy, 4, 0) == (1, 1)
    assert spinn5_chip_coord(0 + dx, 4 + dy, 4, 0) == (0, 0)
    assert spinn5_chip_coord(0 + dx, 5 + dy, 4, 0) == (0, 1)
    assert spinn5_chip_coord(1 + dx, 4 + dy, 4, 0) == (1, 0)
    assert spinn5_chip_coord(1 + dx, 5 + dy, 4, 0) == (1, 1)

    # Types are normal Python integers
    x, y = spinn5_chip_coord(3, 7)
    assert isinstance(x, int)
    assert isinstance(y, int)


def test_spinn5_fpga_link():
    # Check that all outer chips in a SpiNN-5 board are reported as having
    # FPGA links.
    spinn5_chips = set([  # noqa
                                        (4, 7), (5, 7), (6, 7), (7, 7),
                                (3, 6), (4, 6), (5, 6), (6, 6), (7, 6),
                        (2, 5), (3, 5), (4, 5), (5, 5), (6, 5), (7, 5),
                (1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (7, 4),
        (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3), (7, 3),
        (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
        (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
        (0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
    ])
    for x, y in spinn5_chips:
        for link in Links:
            xx = x + link.to_vector()[0]
            yy = y + link.to_vector()[1]
            if (xx, yy) in spinn5_chips:
                assert spinn5_fpga_link(x, y, link) is None
            else:
                assert spinn5_fpga_link(x, y, link) is not None

    # Check a representative subset of the links get the correct numbers
    assert spinn5_fpga_link(0, 0, Links.south_west) == (1, 0)
    assert spinn5_fpga_link(0, 0, Links.south) == (0, 15)

    assert spinn5_fpga_link(0, 3, Links.west) == (1, 7)
    assert spinn5_fpga_link(0, 3, Links.north) == (1, 8)

    assert spinn5_fpga_link(4, 7, Links.west) == (1, 15)
    assert spinn5_fpga_link(4, 7, Links.north) == (2, 0)

    assert spinn5_fpga_link(7, 7, Links.north_east) == (2, 7)
    assert spinn5_fpga_link(7, 7, Links.east) == (2, 8)

    assert spinn5_fpga_link(7, 3, Links.north_east) == (2, 15)
    assert spinn5_fpga_link(7, 3, Links.east) == (0, 0)

    assert spinn5_fpga_link(4, 0, Links.south) == (0, 7)
    assert spinn5_fpga_link(4, 0, Links.south_west) == (0, 8)

    # Make sure things still work when (0, 0) does not exist
    assert spinn5_fpga_link(4, 0, Links.south_west, 4, 0) == (1, 0)
    assert spinn5_fpga_link(0, 4, Links.south_west, 0, 4) == (1, 0)
