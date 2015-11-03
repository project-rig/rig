from collections import OrderedDict

from rig.place_and_route.place.sequential import place

from rig.machine import Machine, Cores


def test_default_ordering():
    # Make sure the default orderings use the vertex and machine ordering
    w, h = 2, 3
    vertices = list(range(w * h))
    vertices_resources = OrderedDict((v, {Cores: 1}) for v in vertices)
    nets = []
    machine = Machine(w, h, chip_resources={Cores: 1})
    constraints = []

    placements = place(vertices_resources, nets, machine, constraints,
                       vertex_order=None, chip_order=None)

    assert placements == {v: c for v, c in zip(vertices, machine)}


def test_vertex_ordering():
    # Make sure the supplied vertex ordering is obeyed
    w, h = 2, 3
    vertices = list(range(w * h))
    vertices_resources = OrderedDict((v, {Cores: 1}) for v in vertices)
    nets = []
    machine = Machine(w, h, chip_resources={Cores: 1})
    constraints = []
    vertex_order = reversed(vertices)

    placements = place(vertices_resources, nets, machine, constraints,
                       vertex_order=vertex_order, chip_order=None)

    assert placements == {v: c for v, c in zip(reversed(vertices), machine)}


def test_chip_ordering():
    # Make sure the supplied chip ordering is obeyed
    w, h = 2, 3
    vertices = list(range(w * h))
    vertices_resources = OrderedDict((v, {Cores: 1}) for v in vertices)
    nets = []
    machine = Machine(w, h, chip_resources={Cores: 1})
    constraints = []
    chip_order = reversed(list(machine))

    placements = place(vertices_resources, nets, machine, constraints,
                       vertex_order=None, chip_order=chip_order)

    assert placements == {v: c for v, c in zip(vertices,
                                               reversed(list(machine)))}


def test_retry():
    # Make sure that we go back and re-try previously filled cores
    v0 = object()
    v1 = object()
    v2 = object()
    vertices_resources = OrderedDict([
        (v0, {Cores: 1}),
        (v1, {Cores: 2}),
        (v2, {Cores: 1}),
    ])
    nets = []
    machine = Machine(2, 1, chip_resources={Cores: 2})
    constraints = []

    placements = place(vertices_resources, nets, machine, constraints)

    assert placements == {
        v0: (0, 0),
        v1: (1, 0),
        v2: (0, 0),
    }
