from rig.place_and_route import Machine
from rig.netlist import Net

from rig.place_and_route.place.rcm import \
    _get_vertices_neighbours, _dfs, _get_connected_subgraphs, _cuthill_mckee, \
    rcm_vertex_order, rcm_chip_order


def test_get_vertices_neighbours():
    # Empty problem
    assert _get_vertices_neighbours([]) == {}

    # Single net should be made bidirectional.
    v0 = "v0"
    v1 = "v1"
    nets = [Net(v0, v1, 2.5)]
    assert _get_vertices_neighbours(nets) == {
        v0: {v1: 2.5},
        v1: {v0: 2.5},
    }

    # Nets should be summed, in both directions
    v0 = "v0"
    v1 = "v1"
    nets = [Net(v0, v1, 2.5), Net(v1, v0, 0.5)]
    assert _get_vertices_neighbours(nets) == {
        v0: {v1: 3.0},
        v1: {v0: 3.0},
    }

    # Self-connections should be allowed (and note that their weight doubles in
    # the same way that other nets gain double their overall weight by becoming
    # bidirectional).
    v0 = "v0"
    v1 = "v1"
    nets = [Net(v0, [v0, v1], 2.5), Net(v1, v0, 0.5)]
    assert _get_vertices_neighbours(nets) == {
        v0: {v0: 5.0, v1: 3.0},
        v1: {v0: 3.0},
    }

    # Multicast nets should be rendered as point-to-point relationships between
    # the source and each sink (rather than an all-to-all connectivity between
    # vertices in the same multicast net).
    v0 = "v0"
    v1 = "v1"
    v2 = "v2"
    nets = [Net(v0, [v1, v2], 2.5)]
    assert _get_vertices_neighbours(nets) == {
        v0: {v1: 2.5, v2: 2.5},
        v1: {v0: 2.5},
        v2: {v0: 2.5},
    }

    # Zero-weight nets should be omitted
    v0 = "v0"
    v1 = "v1"
    nets = [Net(v0, v1, 0)]
    assert _get_vertices_neighbours(nets) == {}

    # Non-connected vertices should also 'appear' in the output (thanks to
    # defaultdict)
    v0 = "v0"
    v1 = "v1"
    v2 = "v2"
    nets = [Net(v0, v1, 2.5)]
    vertices_neighbours = _get_vertices_neighbours(nets)
    assert vertices_neighbours == {
        v0: {v1: 2.5},
        v1: {v0: 2.5},
    }
    assert vertices_neighbours[v2] == {}


def test_dfs():
    # No neighbours at all!
    v0 = "v0"
    assert set(_dfs(v0, {v0: {}})) == set([v0])

    # Disconnected subgraph should not be found
    v0 = "v0"
    v1 = "v1"
    v2 = "v2"
    v3 = "v3"
    v4 = "v4"
    v5 = "v5"
    vertices_neighbours = {
        v0: {v1: 1.0},
        v1: {v0: 1.0, v2: 1.0, v3: 1.0}, v2: {v1: 1.0}, v3: {v1: 1.0},
        v4: {v5: 1.0}, v5: {v4: 1.0},
    }
    assert set(_dfs(v0, vertices_neighbours)) == set([v0, v1, v2, v3])
    assert set(_dfs(v4, vertices_neighbours)) == set([v4, v5])

    # Cycles shouldn't break things
    v0 = "v0"
    v1 = "v1"
    v2 = "v2"
    vertices_neighbours = {
        v0: {v1: 1.0, v2: 1.0},
        v1: {v2: 1.0, v0: 1.0},
        v2: {v0: 1.0, v1: 1.0},
    }
    assert set(_dfs(v0, vertices_neighbours)) == set([v0, v1, v2])


def test_get_connected_subgraphs():
    # Empty graph
    assert _get_connected_subgraphs([], {}) == []

    # Singleton node
    assert _get_connected_subgraphs(["v0"], {"v0": {}}) == [set(["v0"])]

    # Unconnected singletons
    subgraphs = _get_connected_subgraphs(["v0", "v1"], {"v0": {}, "v1": {}})
    assert len(subgraphs) == 2
    assert set(["v0"]) in subgraphs
    assert set(["v1"]) in subgraphs

    # Connected pair
    v0 = "v0"
    v1 = "v1"
    vertices = [v0, v1]
    vertices_neighbours = {v0: {v1: 1.0}, v1: {v0: 1.0}}
    assert _get_connected_subgraphs(vertices, vertices_neighbours) ==\
        [set([v0, v1])]

    # A pair of vertex pairs
    v0 = "v0"
    v1 = "v1"
    v2 = "v2"
    v3 = "v3"
    vertices = [v0, v1, v2, v3]
    vertices_neighbours = {v0: {v1: 1.0}, v1: {v0: 1.0},
                           v2: {v3: 1.0}, v3: {v2: 1.0}}
    subgraphs = _get_connected_subgraphs(vertices, vertices_neighbours)
    assert len(subgraphs) == 2
    assert set([v0, v1]) in subgraphs
    assert set([v2, v3]) in subgraphs


def test_cuthill_mckee():
    # Singleton
    v0 = "v0"
    assert _cuthill_mckee([v0], {v0: {}}) == [v0]

    # Test a case with a trivial and consistent solution: A linear chain of
    # vertices connected by weights of increasing value should be ordered in
    # ascending link order.
    num = 10
    vs = ["v{}".format(n) for n in range(num)]
    vertices_neighbours = {v: {} for v in vs}
    for i in range(num - 1):
        vertices_neighbours[vs[i]][vs[i + 1]] = i + 1.0
        vertices_neighbours[vs[i + 1]][vs[i]] = i + 1.0
    assert _cuthill_mckee(vs, vertices_neighbours) == vs


def test_rcm_vertex_order():
    # Empty
    assert list(rcm_vertex_order({}, [])) == []

    # Single vertex
    v0 = "v0"
    assert list(rcm_vertex_order({v0: {}}, [])) == [v0]

    # Disconnected pair of vertices
    v0 = "v0"
    v1 = "v1"
    assert list(rcm_vertex_order({v0: {}, v1: {}}, [])) in (
        [v0, v1],
        [v1, v0],
    )

    # Connected pair of vertices
    v0 = "v0"
    v1 = "v1"
    vertices_resources = {v0: {}, v1: {}}
    nets = [Net(v0, v1)]
    assert list(rcm_vertex_order(vertices_resources, nets)) in (
        [v0, v1],
        [v1, v0],
    )

    # Seperate pairs of vertices
    v0 = "v0"
    v1 = "v1"
    v2 = "v2"
    v3 = "v3"
    vertices_resources = {v0: {}, v1: {}, v2: {}, v3: {}}
    nets = [Net(v0, v1), Net(v2, v3)]
    assert list(rcm_vertex_order(vertices_resources, nets)) in (
        # v0 & v1 first, all possible orders of each pair
        [v0, v1, v2, v3],
        [v0, v1, v3, v2],
        [v1, v0, v2, v3],
        [v1, v0, v3, v2],
        # v2 & v3 first, all possible orders of each pair
        [v2, v3, v0, v1],
        [v3, v2, v0, v1],
        [v2, v3, v1, v0],
        [v3, v2, v1, v0],
    )


def test_rcm_chip_order():
    # Singleton
    m = Machine(1, 1)
    assert list(rcm_chip_order(m)) == [(0, 0)]

    # Many chips
    m = Machine(4, 2)
    assert sorted(rcm_chip_order(m)) == sorted(m)

    # With dead chips which can be reached by 'working' links. Should not
    # happen in practice but often appear in hand-written 'fake' Machine
    # objects...
    m = Machine(4, 2, dead_chips={(2, 1)})
    assert sorted(rcm_chip_order(m)) == sorted(m)
