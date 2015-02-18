import pytest

from rig.par.routing_tree import RoutingTree


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
        t0 = RoutingTree((0, 0), set([t1, t2]))
        assert set(t0) == set([t0, t1, t2])

        # Grandchildren
        t2 = RoutingTree((2, 0))
        t1 = RoutingTree((1, 0), set([t2]))
        t0 = RoutingTree((0, 0), set([t1]))
        assert set(t0) == set([t0, t1, t2])

        # Inclusion of other types
        t2 = object()
        t1 = RoutingTree((1, 0), set([t2]))
        t0 = RoutingTree((0, 0), set([t1]))
        assert set(t0) == set([t0, t1, t2])

    def test_repr(self):
        # Sanity check for repr. Human-readable representations should at a
        # minimum include the node's type and location.
        t = RoutingTree((123, 321))
        assert "RoutingTree" in repr(t)
        assert "123" in repr(t)
        assert "321" in repr(t)
