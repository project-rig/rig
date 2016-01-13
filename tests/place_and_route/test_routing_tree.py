from rig.place_and_route.routing_tree import RoutingTree

from rig.routing_table import Routes

import pytest


class TestRoutingTree(object):

    def test_init_default(self):
        # Make sure the default initialiser creates no children
        assert RoutingTree((0, 0)).children == set()

    def test_iter(self):
        # Singleton
        t = RoutingTree((0, 0))
        assert set(t) == set([t])

        # Multiple Children
        t2 = RoutingTree((2, 0))
        t1 = RoutingTree((1, 0))
        t0 = RoutingTree((0, 0), set([(Routes.east, t1),
                                      (Routes.west, t2)]))
        assert set(t0) == set([t0, t1, t2])

        # Grandchildren
        t2 = RoutingTree((2, 0))
        t1 = RoutingTree((1, 0), set([(Routes.west, t2)]))
        t0 = RoutingTree((0, 0), set([(Routes.west, t1)]))
        assert set(t0) == set([t0, t1, t2])

        # Inclusion of other types
        t2 = object()
        t1 = RoutingTree((1, 0), set([(Routes.west, t2)]))
        t0 = RoutingTree((0, 0), set([(Routes.west, t1)]))
        assert set(t0) == set([t0, t1, t2])

    def test_repr(self):
        # Sanity check for repr. Human-readable representations should at a
        # minimum include the node's type and location.
        t = RoutingTree((123, 321))
        assert "RoutingTree" in repr(t)
        assert "123" in repr(t)
        assert "321" in repr(t)

    def test_traverse(self):
        # Construct a tree and then check that we traverse it correctly.
        #                          - north -> (1, 1) - 5 -> None
        #                        /
        # (0, 0) - east -> (1, 0) - east -> (2, 0)
        #                       \
        #                        \- south -> (1, -1) - east -> (2, -1) -> 2
        t0 = RoutingTree((2, -1), {(Routes.core(2), None)})
        t1 = RoutingTree((1, -1), {(Routes.east, t0)})
        t2 = RoutingTree((1, 1), {(Routes.core(5), None)})
        t3 = RoutingTree((2, 0), {(None, None)})
        t4 = RoutingTree((1, 0), {(Routes.north, t2),
                                  (Routes.east, t3),
                                  (Routes.south, t1)})
        tree = RoutingTree((0, 0), {(Routes.east, t4)})

        # Traverse the tree manually
        tip = tree.traverse()
        assert (None, (0, 0), {Routes.east}) == next(tip)

        assert (Routes.east, (1, 0), {Routes.north,
                                      Routes.east,
                                      Routes.south}) == next(tip)

        # Children of (1, 0)
        for _ in range(3):
            direction, chip, out_directions = next(tip)
            assert direction in {Routes.north, Routes.east, Routes.south}

            if direction is Routes.north:
                assert chip == (1, 1)
                assert out_directions == {Routes.core(5)}
            elif direction is Routes.east:
                assert chip == (2, 0)
                assert out_directions == set()
            else:
                assert chip == (1, -1)
                assert out_directions == {Routes.east}

        # Child of (1, -1)
        assert (Routes.east, (2, -1), {Routes.core(2)}) == next(tip)

        # Finished traversal
        with pytest.raises(StopIteration):
            next(tip)
