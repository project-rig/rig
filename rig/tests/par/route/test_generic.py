"""Generic correctness tests applicable to all routing algorithms."""

import pytest

from collections import deque

from rig.machine import Machine, Links

from rig.routing_table import RoutingTree

from rig.netlist import Net

from rig.par.constraints import RouteToLinkConstraint

from rig.par.exceptions import MachineHasDisconnectedSubregion, \
    InvalidConstraintError

from rig.par.route.util import links_between

from rig.par import route as default_route
from rig.par.route.ner import route as ner_route

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
    assert algorithm(vertices_resources, [], machine, [], placements,
                     **kwargs) \
        == []

    # Test with a null machine with no vertices and nets
    machine = Machine(0, 0, chip_resources={})
    assert algorithm({}, [], machine, [], {}, **kwargs) == []


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


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_correctness(algorithm, kwargs):
    # Run a few small Nets on a slightly broken machine and check the resulting
    # RoutingTrees are trees which actually connect the nets correctly.
    machine = Machine(10, 10,
                      dead_chips=set([(1, 1)]),
                      dead_links=set([(0, 0, Links.north)]))

    # [(vertices_resources, placements, nets), ...]
    test_cases = []

    # Self-loop
    v0 = object()
    v1 = object()
    vertices_resources = {v0: {}, v1: {}}
    placements = {v0: (0, 0), v1: (0, 0)}
    nets = [Net(v0, [v1])]
    test_cases.append((vertices_resources, placements, nets))

    # Point-to-neighbour net, with no direct obstruction
    placements = {v0: (0, 0), v1: (1, 0)}
    test_cases.append((vertices_resources, placements, nets))

    # Point-to-point net, with no direct obstruction
    placements = {v0: (0, 0), v1: (5, 0)}
    test_cases.append((vertices_resources, placements, nets))

    # Point-to-point net, with link obstruction
    placements = {v0: (0, 0), v1: (0, 1)}
    test_cases.append((vertices_resources, placements, nets))

    # Point-to-point net, with chip obstruction
    placements = {v0: (0, 0), v1: (2, 2)}
    test_cases.append((vertices_resources, placements, nets))

    # Point-to-point net with potential wrap-around
    placements = {v0: (0, 0), v1: (9, 9)}
    test_cases.append((vertices_resources, placements, nets))

    # Multicast route to cores on same chip
    v_src = object()
    v_sinks = [object() for _ in range(10)]
    vertices_resources = {v: {} for v in [v_src] + v_sinks}
    placements = {v: (0, 0) for v in [v_src] + v_sinks}
    nets = [Net(v_src, v_sinks)]
    test_cases.append((vertices_resources, placements, nets))

    # Multicast route to cores on different chips
    placements = {v: (x, 2) for x, v in enumerate(v_sinks)}
    placements[v_src] = (0, 0)
    test_cases.append((vertices_resources, placements, nets))

    # Two identical nets
    nets = [Net(v_src, v_sinks), Net(v_src, v_sinks)]
    test_cases.append((vertices_resources, placements, nets))

    # A ring-network of unicast nets
    vertices = [object() for _ in range(10)]
    vertices_resources = {v: {} for v in vertices}
    placements = {v: (x, 0) for x, v in enumerate(vertices)}
    nets = [Net(vertices[i], [vertices[(i + 1) % len(vertices)]])
            for i in range(len(vertices))]
    test_cases.append((vertices_resources, placements, nets))

    # Broadcast nets from every vertex
    nets = [Net(v, vertices) for v in vertices]
    test_cases.append((vertices_resources, placements, nets))

    # Run through each test case simply ensuring a valid net has been created
    # for every listed net
    for vertices_resources, placements, nets in test_cases:
        routes = algorithm(vertices_resources, nets, machine, [], placements,
                           **kwargs)

        # Should have one route per net
        assert len(routes) == len(nets)

        # A list of nets which will be removed when a matching route is found
        unseen_nets = nets[:]
        for route in routes:
            # Make sure the route is a tree and does not use any dead links
            assert_fully_connected(route, machine)

            # Make sure there is a net which matches this route exactly
            source_chip = route.chip
            sink_vertices = set(v for v in route
                                if not isinstance(v, RoutingTree))
            for unseen_net in unseen_nets:
                same_source = placements[unseen_net.source] == source_chip
                same_sinks = set(v for v in unseen_net.sinks) \
                    == sink_vertices
                if same_source and same_sinks:
                    unseen_nets.remove(unseen_net)
                    break
            else:
                assert False, "No net matching route {}".format(route)

        # Make sure no net was left unrouted
        assert unseen_nets == []


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
    nets = [Net(v0, [v1])]
    with pytest.raises(MachineHasDisconnectedSubregion):
        algorithm(vertices_resources, nets, machine, [], placements, **kwargs)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_route_to_link(algorithm, kwargs):
    # Test that RouteToLinkConstraint results in a vertex not being added to a
    # RoutingTree but a Link instead.
    machine = Machine(10, 10,
                      dead_chips=set([(1, 1)]),
                      dead_links=set([(0, 0, Links.north)]))

    # Connect straight to a local link (attempt to get to both a dead and alive
    # link: both should work).
    for link in [Links.east, Links.north]:
        v0 = object()
        v1 = object()
        vertices_resources = {v0: {}, v1: {}}
        placements = {v0: (0, 0), v1: (0, 0)}
        nets = [Net(v0, [v1])]
        constraints = [RouteToLinkConstraint(v1, link)]
        routes = algorithm(vertices_resources, nets, machine, constraints,
                           placements, **kwargs)

        # Just one net to route
        assert len(routes) == 1
        route = routes[0]

        # Should be a valid tree
        assert_fully_connected(route, machine)

        # Check only the destination chip and link are present
        assert v0 not in route
        assert v1 not in route
        for node in route:
            if isinstance(node, RoutingTree):
                assert node.chip == (0, 0)
            else:
                assert node is link
        assert len(list(route)) == 2

    # Connect straight to a local link and a chip
    v0 = object()
    v1 = object()
    v2 = object()
    vertices_resources = {v0: {}, v1: {}, v2: {}}
    placements = {v0: (0, 0), v1: (2, 1), v2: (1, 2)}
    nets = [Net(v0, [v1, v2])]
    constraints = [RouteToLinkConstraint(v1, Links.east)]
    routes = algorithm(vertices_resources, nets, machine, constraints,
                       placements, **kwargs)

    # Just one net to route
    assert len(routes) == 1
    route = routes[0]

    # Should be a valid tree
    assert_fully_connected(route, machine)

    # Check that only the unconstrained sink is present
    assert v2 in route
    assert v1 not in route
    assert Links.east in route
