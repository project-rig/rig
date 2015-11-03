import pytest

from rig.netlist import Net

from rig.place_and_route.place.breadth_first import breadth_first_vertex_order


def test_empty():
    assert list(breadth_first_vertex_order({}, [])) == []


@pytest.mark.parametrize("with_net", [True, False])
def test_singleton(with_net):
    v0 = object()

    if with_net:
        nets = [Net(v0, v0)]
    else:
        nets = []

    assert list(breadth_first_vertex_order({v0: {}}, nets)) == [v0]


@pytest.mark.parametrize("with_net", [True, False])
def test_disconnected(with_net):
    # Should include both vertices when we provide two vertices which aren't
    # connected together.
    v0 = object()
    v1 = object()

    if with_net:
        nets = [Net(v0, v0)]
    else:
        nets = []

    assert set(breadth_first_vertex_order({v0: {}, v1: {}}, nets)) == set([
        v0, v1
    ])


def test_group_together():
    # Given a set of vertices with nets linking them into a cycle, they should
    # be produced in order.
    v0 = object()
    v1 = object()
    v2 = object()
    v3 = object()
    v4 = object()
    v5 = object()

    vertices_resources = {v: {} for v in [v0, v1, v2, v3, v4, v5]}
    nets = [
        Net(v0, [v1, v2]),
        Net(v3, [v4, v5]),
    ]

    order = list(breadth_first_vertex_order(vertices_resources, nets))

    # Should have the right set of vertices
    assert set(order) == set(vertices_resources)

    # Should do each group as a group
    assert ((set(order[0:3]) == set([v0, v1, v2])
             and set(order[3:6]) == set([v3, v4, v5]))
            or (set(order[0:3]) == set([v3, v4, v5])
                and set(order[3:6]) == set([v0, v1, v2])))
