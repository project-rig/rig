from ..geometry import concentric_hexagons, to_xyz, minimise_xyz, \
    shortest_mesh_path_length, shortest_mesh_path, \
    shortest_torus_path_length, shortest_torus_path


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
                if not unseen_minimiseds:
                    break
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
                if not unseen_neg_minimiseds:
                    break
            assert unseen_neg_minimiseds == set(), \
                (start, end, width, height, neg_minimiseds)
