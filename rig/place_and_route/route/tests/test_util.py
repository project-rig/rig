from rig.place_and_route.route.util import \
    longest_dimension_first, links_between

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
    for _ in range(1000):  # pragma: no branch
        first_move = list(longest_dimension_first((1, 1, 1)))[0]
        if first_move == (1, 0):
            generated_x_first = True
        elif first_move == (0, 1):
            generated_y_first = True
        elif first_move == (-1, -1):
            generated_z_first = True
        else:
            assert False, "Unexpected move made!"  # pragma: no cover
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


def test_links_between():
    # Singleton torus system should be connected to itself on all links
    machine = Machine(1, 1)
    assert links_between((0, 0), (0, 0), machine) == set(Links)

    # If some links are down, these should be omitted
    machine = Machine(1, 1, dead_links=set([(0, 0, Links.north)]))
    assert (links_between((0, 0), (0, 0), machine) ==  # pragma: no branch
            set(l for l in Links if l != Links.north))

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
