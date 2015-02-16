import pytest

from six import next

from rig.par.route.util import \
    longest_dimension_first, to_xyz, minimise_xyz, \
    shortest_mesh_path_length, shortest_mesh_path, \
    shortest_torus_path_length, shortest_torus_path, \
    has_wrap_around_links, links_between

from rig.machine import Machine, Links


def test_longest_dimension_first():
    # Null test
    assert list(longest_dimension_first((0, 0, 0))) == []

    # Single hop in each dimension
    assert list(longest_dimension_first((1, 0, 0))) == [(1, 0)]
    assert list(longest_dimension_first((0, 1, 0))) == [(0, 1)]
    assert list(longest_dimension_first((0, 0, 1))) == [(-1, -1)]

    # Negative single hop in each dimension
    assert list(longest_dimension_first((-1, 0, 0))) == [(-1, 0)]
    assert list(longest_dimension_first((0, -1, 0))) == [(0, -1)]
    assert list(longest_dimension_first((0, 0, -1))) == [(1, 1)]

    # Single hop from alternative starting point
    assert list(longest_dimension_first((1, 0, 0), (10, 100))) == [(11, 100)]
    assert list(longest_dimension_first((0, 1, 0), (10, 100))) == [(10, 101)]
    assert list(longest_dimension_first((0, 0, 1), (10, 100))) == [(9, 99)]

    # Negative single hop from alternative starting point
    assert list(longest_dimension_first((-1, 0, 0), (10, 100))) == [(9, 100)]
    assert list(longest_dimension_first((0, -1, 0), (10, 100))) == [(10, 99)]
    assert list(longest_dimension_first((0, 0, -1), (10, 100))) == [(11, 101)]

    # Test wrap-around of single hop
    assert list(longest_dimension_first((1, 0, 0), width=1, height=1)) \
        == [(0, 0)]
    assert list(longest_dimension_first((0, 1, 0), width=1, height=1)) \
        == [(0, 0)]
    assert list(longest_dimension_first((0, 0, 1), width=1, height=1)) \
        == [(0, 0)]
    assert list(longest_dimension_first((-1, 0, 0), width=1, height=1)) \
        == [(0, 0)]
    assert list(longest_dimension_first((0, -1, 0), width=1, height=1)) \
        == [(0, 0)]
    assert list(longest_dimension_first((0, 0, -1), width=1, height=1)) \
        == [(0, 0)]

    # Test wrap-around in each direction
    assert list(longest_dimension_first((2, 0, 0), width=2, height=2)) \
        == [(1, 0), (0, 0)]
    assert list(longest_dimension_first((0, 2, 0), width=2, height=2)) \
        == [(0, 1), (0, 0)]
    assert list(longest_dimension_first((0, 0, 2), width=2, height=2)) \
        == [(1, 1), (0, 0)]
    assert list(longest_dimension_first((-2, 0, 0), width=2, height=2)) \
        == [(1, 0), (0, 0)]
    assert list(longest_dimension_first((0, -2, 0), width=2, height=2)) \
        == [(0, 1), (0, 0)]
    assert list(longest_dimension_first((0, 0, -2), width=2, height=2)) \
        == [(1, 1), (0, 0)]

    # Test wrap-around with different width & height
    assert list(longest_dimension_first((0, 0, 1), width=2, height=3)) \
        == [(1, 2)]

    # Test multiple hops on single dimension
    assert list(longest_dimension_first((2, 0, 0))) \
        == [(1, 0), (2, 0)]
    assert list(longest_dimension_first((0, 2, 0))) \
        == [(0, 1), (0, 2)]
    assert list(longest_dimension_first((0, 0, 2))) \
        == [(-1, -1), (-2, -2)]

    # Test dimension ordering with all positive magnitudes and some zero
    assert list(longest_dimension_first((2, 1, 0))) \
        == [(1, 0), (2, 0), (2, 1)]
    assert list(longest_dimension_first((0, 2, 1))) \
        == [(0, 1), (0, 2), (-1, 1)]
    assert list(longest_dimension_first((1, 0, 2))) \
        == [(-1, -1), (-2, -2), (-1, -2)]
    assert list(longest_dimension_first((0, 1, 2))) \
        == [(-1, -1), (-2, -2), (-2, -1)]

    # Test dimension ordering with all positive magnitudes and no zeros
    assert list(longest_dimension_first((3, 2, 1))) \
        == [(1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (2, 1)]
    assert list(longest_dimension_first((1, 3, 2))) \
        == [(0, 1), (0, 2), (0, 3), (-1, 2), (-2, 1), (-1, 1)]
    assert list(longest_dimension_first((2, 1, 3))) \
        == [(-1, -1), (-2, -2), (-3, -3), (-2, -3), (-1, -3), (-1, -2)]
    assert list(longest_dimension_first((1, 2, 3))) \
        == [(-1, -1), (-2, -2), (-3, -3), (-3, -2), (-3, -1), (-2, -1)]

    # Test dimension ordering with mixed sign magnitudes
    assert list(longest_dimension_first((1, -2, 0))) \
        == [(0, -1), (0, -2), (1, -2)]
    assert list(longest_dimension_first((-2, 1, 0))) \
        == [(-1, 0), (-2, 0), (-2, 1)]

    # Test that given ambiguity, ties are broken randomly. Note: we
    # just test that in a large number of calls, each option is tried at least
    # once. This test *could* fail due to random chance but the probability of
    # this should be *very* low. We do not assert the fairness of the
    # distribution.
    generated_x_first = False
    generated_y_first = False
    generated_z_first = False
    for _ in range(1000):
        first_move = list(longest_dimension_first((1, 1, 1)))[0]
        if first_move == (1, 0):
            generated_x_first = True
        elif first_move == (0, 1):
            generated_y_first = True
        elif first_move == (-1, -1):
            generated_z_first = True
        else:
            assert False, "Unexpected move made!"
        if generated_x_first and generated_y_first and generated_z_first:
            break
    assert generated_x_first
    assert generated_y_first
    assert generated_z_first

    # The "just try some stuff" test: Check that correct number of steps is
    # given for a a selection of larger vectors.
    for vector in [(0, 0, 0), (1, 1, 1), (1, -1, 0),  # Test sanity checks
                   (10, 10, 10), (10, -10, 5), (10, 20, 30)]:
        assert len(list(longest_dimension_first(vector))) \
            == sum(map(abs, vector)), \
            vector


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
            for _ in range(1000):
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

            for _ in range(1000):
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


def test_has_wrap_around_links():
    # Test singleton with wrap-arounds
    machine = Machine(1, 1)
    assert has_wrap_around_links(machine)
    assert has_wrap_around_links(machine, 1.0)
    assert has_wrap_around_links(machine, 0.1)

    # Test singleton with dead chip
    machine = Machine(1, 1, dead_chips=set([(0, 0)]))
    assert not has_wrap_around_links(machine)
    assert not has_wrap_around_links(machine, 1.0)
    assert not has_wrap_around_links(machine, 0.1)

    # Test singleton with one dead link
    machine = Machine(1, 1, dead_links=set([(0, 0, Links.north)]))
    assert has_wrap_around_links(machine, 5.0 / 6.0)
    assert not has_wrap_around_links(machine, 1.0)

    # Test fully-working larger machine
    machine = Machine(10, 10)
    assert has_wrap_around_links(machine)
    assert has_wrap_around_links(machine, 1.0)
    assert has_wrap_around_links(machine, 0.1)

    # Test larger machine with 50% dead links (note that we simply kill 50% of
    # links on border chips, not all chips, ensuring this function probably
    # isn't testing all links, just those on the borders)
    machine = Machine(10, 10, dead_links=set(
        [(x, y, link)
         for x in range(10)
         for y in range(10)
         for link in [Links.north, Links.west, Links.south_west]
         if x == 0 or y == 0]))
    assert not has_wrap_around_links(machine, 1.0)
    assert has_wrap_around_links(machine, 0.5)
    assert has_wrap_around_links(machine, 0.1)


def test_links_between():
    # Singleton torus system should be connected to itself on all links
    machine = Machine(1, 1)
    assert links_between((0, 0), (0, 0), machine) == set(Links)

    # If some links are down, these should be omitted
    machine = Machine(1, 1, dead_links=set([(0, 0, Links.north)]))
    assert links_between((0, 0), (0, 0), machine) \
        == set(l for l in Links if l != Links.north)

    # Should work the same in large system
    machine = Machine(10, 10, dead_links=set([(4, 4, Links.north)]))
    assert links_between((4, 4), (5, 4), machine) == set([Links.east])
    assert links_between((4, 4), (3, 4), machine) == set([Links.west])
    assert links_between((4, 4), (3, 3), machine) == set([Links.south_west])
    assert links_between((4, 4), (4, 3), machine) == set([Links.south])
    assert links_between((4, 4), (5, 5), machine) == set([Links.north_east])
    assert links_between((4, 4), (4, 5), machine) == set([])  # Link is dead

    # Non-adjacent chips shouldn't be connected
    assert links_between((0, 0), (2, 2), machine) == set([])
