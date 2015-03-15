"""Generic correctness tests applicable to all routing algorithms."""

import pytest

from collections import deque

from rig.machine import Machine, Links, Cores

from rig.netlist import Net

from rig.place_and_route.routing_tree import RoutingTree

from rig.place_and_route.constraints import RouteEndpointConstraint

from rig.place_and_route.exceptions import MachineHasDisconnectedSubregion

from rig.place_and_route.route.util import links_between

from rig.place_and_route import route as default_route
from rig.place_and_route.route.ner import route as ner_route

from rig.routing_table import Routes

# This dictionary should be updated to contain all implemented algorithms along
# with applicable keyword arguments.
ALGORITHMS_UNDER_TEST = [(default_route, {}),
                         (ner_route, {}),
                         # Equivalent to longest-dimension-first
                         (ner_route, {"radius": 0})]


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_null_route(algorithm, kwargs):
    """Test algorithms correctly handle cases where nothing gets routed.
    """
    # Test with some vertices with no nets
    machine = Machine(2, 2)
    vertices_resources = {object(): {} for _ in range(4)}
    placements = {v: (i % 2, i//2) for i, v in enumerate(vertices_resources)}
    allocation = {v: {} for v in vertices_resources}
    assert algorithm(vertices_resources, [], machine, [], placements,
                     allocation, **kwargs) \
        == {}

    # Test with a null machine with no vertices and nets
    machine = Machine(0, 0, chip_resources={})
    assert algorithm({}, [], machine, [], {}, {}, **kwargs) == {}


def assert_fully_connected(root, machine):
    """Assert that the supplied routing tree is a fully-connected sub-tree of
    the machine.
    """
    visited = set()
    to_visit = deque([root])
    while to_visit:
        node = to_visit.popleft()
        assert node.chip in machine

        assert node.chip not in visited, "Cycle exists in tree"
        visited.add(node.chip)

        for child in node.children:
            if isinstance(child, RoutingTree):
                assert links_between(node.chip, child.chip, machine)
                to_visit.append(child)


def assert_equivilent(route, net, placements, allocation, constraints=[]):
    """Assert that the given routing tree fulfils the needs of the net."""
    # Assert that the route starts with the nets' source
    assert placements[net.source] == route.chip

    # Net should visit all locations where a net's sink exists
    assert (  # pragma: no branch
        set(n.chip for n in route if isinstance(n, RoutingTree)).issuperset(
            set(placements[v] for v in net.sinks)))

    # Enumerate the locations and types of all terminations of the tree.
    endpoints = set()
    for node in route:
        if isinstance(node, RoutingTree):
            for child in node.children:
                if not isinstance(child, RoutingTree):
                    x, y = node.chip
                    endpoints.add((x, y, child))

    # Enumerate all vertices which are constrained to a certain route
    endpoint_constraints = {}
    for constraint in constraints:
        if isinstance(constraint,  # pragma: no branch
                      RouteEndpointConstraint):
            endpoint_constraints[constraint.vertex] = constraint.route

    # Ensure all vertices in the net have a corresponding endpoint
    for vertex in net.sinks:
        x, y = placements[vertex]

        if vertex in endpoint_constraints:
            route = endpoint_constraints[vertex]
            endpoint = (x, y, route)
            assert endpoint in endpoints
            endpoints.remove(endpoint)
        else:
            cores = allocation[vertex].get(Cores, slice(0, 0))
            for core in range(cores.start, cores.stop):
                endpoint = (x, y, Routes.core(core))
                assert endpoint in endpoints
                endpoints.remove(endpoint)

    # All endpoints should have been accounted for
    assert not endpoints


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_correctness(algorithm, kwargs):
    # Run a few small Nets on a slightly broken machine and check the resulting
    # RoutingTrees are trees which actually connect the nets correctly.
    machine = Machine(10, 10,
                      dead_chips=set([(1, 1)]),
                      dead_links=set([(0, 0, Links.north)]))

    # [(vertices_resources, placements, nets, allocation), ...]
    test_cases = []

    # Self-loop
    v0 = object()
    v1 = object()
    vertices_resources = {v0: {Cores: 1}, v1: {Cores: 1}}
    placements = {v0: (0, 0), v1: (0, 0)}
    allocation = {v0: {Cores: slice(0, 1)}, v1: {Cores: slice(1, 2)}}
    nets = [Net(v0, [v1])]
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Point-to-neighbour net, with no direct obstruction
    placements = {v0: (0, 0), v1: (1, 0)}
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Point-to-point net, with no direct obstruction
    placements = {v0: (0, 0), v1: (5, 0)}
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Point-to-point net, with link obstruction
    placements = {v0: (0, 0), v1: (0, 1)}
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Point-to-point net, with chip obstruction
    placements = {v0: (0, 0), v1: (2, 2)}
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Point-to-point net with potential wrap-around
    placements = {v0: (0, 0), v1: (9, 9)}
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Multicast route to cores on same chip
    v_src = object()
    v_sinks = [object() for _ in range(10)]
    vertices_resources = {v: {Cores: 1} for v in [v_src] + v_sinks}
    placements = {v: (0, 0) for v in [v_src] + v_sinks}
    allocation = {v: {Cores: slice(i, i + 1)}
                  for i, v in enumerate(placements)}
    nets = [Net(v_src, v_sinks)]
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Multicast route to cores on different chips
    placements = {v: (x, 2) for x, v in enumerate(v_sinks)}
    placements[v_src] = (0, 0)
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Two identical nets
    nets = [Net(v_src, v_sinks), Net(v_src, v_sinks)]
    test_cases.append((vertices_resources, placements, nets, allocation))

    # A ring-network of unicast nets
    vertices = [object() for _ in range(10)]
    vertices_resources = {v: {Cores: 1} for v in vertices}
    placements = {v: (x, 0) for x, v in enumerate(vertices)}
    allocation = {v: {Cores: slice(0, 1)} for v in vertices}
    nets = [Net(vertices[i], [vertices[(i + 1) % len(vertices)]])
            for i in range(len(vertices))]
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Broadcast nets from every vertex
    nets = [Net(v, vertices) for v in vertices]
    test_cases.append((vertices_resources, placements, nets, allocation))

    # Run through each test case simply ensuring a valid net has been created
    # for every listed net
    for vertices_resources, placements, nets, allocation in test_cases:
        routes = algorithm(vertices_resources, nets, machine, [], placements,
                           allocation, **kwargs)

        # Should have one route per net
        assert set(routes) == set(nets)

        # A list of nets which will be removed when a matching route is found
        for net in nets:
            route = routes[net]
            # Make sure the route is a tree and does not use any dead links
            assert_fully_connected(route, machine)

            # Make sure the net matches this route exactly
            assert_equivilent(route, net, placements, allocation)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_impossible(algorithm, kwargs):
    # Given a not-connected network, check that routing fails as expected
    machine = Machine(2, 1, dead_links=set((x, 0, l)
                                           for x in range(2)
                                           for l in Links))

    v0 = object()
    v1 = object()
    vertices_resources = {v0: {}, v1: {}}
    placements = {v0: (0, 0), v1: (1, 0)}
    allocation = {v0: {}, v1: {}}
    nets = [Net(v0, [v1])]
    with pytest.raises(MachineHasDisconnectedSubregion):
        algorithm(vertices_resources, nets, machine, [], placements,
                  allocation, **kwargs)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_route_endpoint_constraint(algorithm, kwargs):
    # Test that RouteEndpointConstraint results in a core route not being added
    # to a RoutingTree but the supplied Route instead.
    machine = Machine(10, 10,
                      dead_chips=set([(1, 1)]),
                      dead_links=set([(0, 0, Links.north)]))

    # Connect straight to a local link (attempt to get to both a dead and alive
    # link: both should work).
    for endpoint in [Routes.east, Routes.north]:
        v0 = object()
        v1 = object()
        vertices_resources = {v0: {}, v1: {}}
        placements = {v0: (0, 0), v1: (0, 0)}
        allocation = {v0: {}, v1: {}}
        nets = [Net(v0, [v1])]
        constraints = [RouteEndpointConstraint(v1, endpoint)]
        routes = algorithm(vertices_resources, nets, machine, constraints,
                           placements, allocation, **kwargs)

        # Just one net to route
        assert len(routes) == 1
        assert set(nets) == set(routes)
        route = routes[nets[0]]

        # Should be a valid tree and equivilent to the net
        assert_fully_connected(route, machine)
        assert_equivilent(route, nets[0], placements, allocation, constraints)

    # Connect straight to a local link and a chip
    v0 = object()
    v1 = object()
    v2 = object()
    vertices_resources = {v0: {Cores: 1}, v1: {}, v2: {Cores: 1}}
    placements = {v0: (0, 0), v1: (2, 1), v2: (1, 2)}
    allocation = {v0: {Cores: slice(0, 1)}, v1: {}, v2: {Cores: slice(0, 1)}}
    nets = [Net(v0, [v1, v2])]
    constraints = [RouteEndpointConstraint(v1, Routes.east)]
    routes = algorithm(vertices_resources, nets, machine, constraints,
                       placements, allocation, **kwargs)

    # Just one net to route
    assert len(routes) == 1
    assert set(nets) == set(routes)
    route = routes[nets[0]]

    # Should be a valid tree and equivilent to the net
    assert_fully_connected(route, machine)
    assert_equivilent(route, nets[0], placements, allocation, constraints)
