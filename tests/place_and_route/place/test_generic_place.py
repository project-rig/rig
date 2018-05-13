"""Generic correctness tests applicable to all placement algorithms.

Note that these tests are intended to be so easy that it will just weed out
fundamental failures of placement algorithms. Note that in general,
however, it is perfectly acceptable for problems to exist which not all
placers can handle.
"""

import pytest

import random

from collections import OrderedDict

from six import iteritems

from rig.netlist import Net

from rig.links import Links

from rig.place_and_route.machine import Machine, Cores

from rig.place_and_route.exceptions import InsufficientResourceError
from rig.place_and_route.exceptions import InvalidConstraintError

from rig.place_and_route.constraints import LocationConstraint, \
    ReserveResourceConstraint, SameChipConstraint

from rig.place_and_route import place as default_place
from rig.place_and_route.place.sequential import place as sequential_place
from rig.place_and_route.place.breadth_first \
    import place as breadth_first_place
from rig.place_and_route.place.hilbert import place as hilbert_place
from rig.place_and_route.place.sa import place as sa_place
from rig.place_and_route.place.rand import place as rand_place
from rig.place_and_route.place.rcm import place as rcm_place

from rig.place_and_route.place.sa.python_kernel import PythonKernel


# Get a list of all available kernels
try:
    from rig.place_and_route.place.sa.c_kernel import CKernel
except ImportError:  # pragma: no cover
    CKernel = None


# This dictionary should be updated to contain all implemented algorithms along
# with applicable keyword arguments.
ALGORITHMS_UNDER_TEST = [(default_place, {}),
                         (sequential_place, {}),
                         (hilbert_place, {}),
                         (hilbert_place, {"breadth_first": False}),
                         (breadth_first_place, {}),
                         # Test default placer kernel
                         (sa_place, {}),
                         # Test using other kernels (when available)
                         (sa_place, {"kernel": PythonKernel}),
                         pytest.mark.skipif("CKernel is None")(
                             (sa_place, {"kernel": CKernel})),
                         # Testing with effort = 0 tests the initial (random)
                         # placement solutions of the SA placer.
                         (sa_place, {"effort": 0.0}),
                         (rand_place, {}),
                         (rcm_place, {})]


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_null_placement(algorithm, kwargs):
    """Test algorithms correctly handle placements with no vertices to
    place.
    """
    # Test with a non-null machine
    machine = Machine(2, 2)
    assert algorithm({}, [], machine, [], **kwargs) == {}

    # Test with a null machine
    machine = Machine(0, 0)
    assert algorithm({}, [], machine, [], **kwargs) == {}


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_impossible(algorithm, kwargs):
    """Test that algorithms fail to place things which simply can't fit."""

    # Putting in just one vertex with a null machine
    machine = Machine(0, 0)
    with pytest.raises(InsufficientResourceError):
        algorithm({object(): {Cores: 1}}, [], machine, [], **kwargs)

    # Putting in just one vertex in a machine where all chips are dead
    machine = Machine(2, 2,
                      dead_chips=set((x, y)
                                     for x in range(2)
                                     for y in range(2)))
    with pytest.raises(InsufficientResourceError):
        algorithm({object(): {Cores: 1}}, [], machine, [], **kwargs)

    # Putting in a vertex which uses more resources than are available on any
    # chip.
    machine = Machine(2, 2, chip_resources={Cores: 1})
    with pytest.raises(InsufficientResourceError):
        algorithm({object(): {Cores: 2}}, [], machine, [], **kwargs)

    # Putting in a vertex which uses resources than are only available on a
    # dead chip.
    machine = Machine(2, 2,
                      chip_resources={Cores: 1},
                      chip_resource_exceptions={(0, 0): {Cores: 2}},
                      dead_chips=set([(0, 0)]))
    with pytest.raises(InsufficientResourceError):
        algorithm({object(): {Cores: 2}}, [], machine, [], **kwargs)


def assert_valid(placement, vertices, machine):
    """Given a placement, make sure it doesn't break any rules."""
    used_chips = set()
    for v in vertices:
        assert v in placement
        assert placement[v] in machine
        assert placement[v] not in used_chips
        used_chips.add(v)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_singleton_single_machine(algorithm, kwargs):
    # Putting in just one vertex in a singleton machine.
    machine = Machine(1, 1)
    vertex = object()
    assert algorithm({vertex: {Cores: 1}}, [], machine, [], **kwargs) \
        == {vertex: (0, 0)}


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_singleton_large_machine(algorithm, kwargs):
    # Putting in just one vertex into a large machine
    machine = Machine(10, 10)
    vertex = object()
    placement = algorithm({vertex: {Cores: 1}}, [], machine, [], **kwargs)
    assert vertex in placement
    assert placement[vertex] in machine


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_multiple_single_machine(algorithm, kwargs):
    # Putting in multiple vertices in a singleton machine with adequate
    # resources.
    machine = Machine(1, 1, chip_resources={Cores: 8})
    vertices = [object() for _ in range(8)]
    assert algorithm({v: {Cores: 1} for v in vertices},  # pragma: no branch
                     [], machine, [], **kwargs) \
        == {v: (0, 0) for v in vertices}


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_multiple_connected_single_machine(algorithm, kwargs):
    # Putting in multiple connected vertices in a singleton machine with
    # adequate resources.
    machine = Machine(1, 1, chip_resources={Cores: 8})
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[1:])]
    assert algorithm({v: {Cores: 1} for v in vertices},  # pragma: no branch
                     nets, machine, [], **kwargs) \
        == {v: (0, 0) for v in vertices}


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_multiple_large_machine(algorithm, kwargs):
    # Putting in small number of disconnected vertices into a large machine
    # with adequate resources.
    machine = Machine(10, 10, chip_resources={Cores: 1})
    vertices = [object() for _ in range(8)]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          [], machine, [], **kwargs)
    assert_valid(placement, vertices, machine)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_multiple_connected_large_machine(algorithm, kwargs):
    # Putting in small number of connected vertices into a large machine with
    # adequate resources.
    machine = Machine(10, 10, chip_resources={Cores: 1})
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[:])]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          nets, machine, [], **kwargs)
    assert_valid(placement, vertices, machine)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_multiple_connected_large_machine_no_wrap(algorithm, kwargs):
    # Putting in small number of connected vertices into a large machine with
    # adequate resources but no wrap-around links.
    machine = Machine(10, 10, chip_resources={Cores: 1})
    for x in range(10):
        machine.dead_links.add((x, 0, Links.south))
        machine.dead_links.add((x, 0, Links.south_west))
        machine.dead_links.add((x, 9, Links.north))
        machine.dead_links.add((x, 9, Links.north_east))
    for y in range(10):
        machine.dead_links.add((0, y, Links.west))
        machine.dead_links.add((0, y, Links.south_west))
        machine.dead_links.add((9, y, Links.east))
        machine.dead_links.add((9, y, Links.north_east))
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[:])]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          nets, machine, [], **kwargs)
    assert_valid(placement, vertices, machine)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_multiple_disconnected_large_machine(algorithm, kwargs):
    # Putting in small number of disconnected groups of vertices into a large
    # machine with adequate resources.
    machine = Machine(10, 10, chip_resources={Cores: 1})
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[1:4]),
            Net(vertices[4], vertices[5:])]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          nets, machine, [], **kwargs)
    assert_valid(placement, vertices, machine)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_multiple_disconnected_large_machine_multiple_cores(algorithm, kwargs):
    # Putting in small number of disconnected groups of vertices into a large
    # machine with adequate resources such that all vertices should fit within
    # a single chip.
    machine = Machine(2, 1, chip_resources={Cores: 8})
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[1:4]),
            Net(vertices[4], vertices[5:])]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          nets, machine, [], **kwargs)
    assert_valid(placement, vertices, machine)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_location_constraint(algorithm, kwargs):
    """Test that the LocationConstraint is respected."""
    # Should be able to constrain a single vertex in a small system
    machine = Machine(1, 1)
    vertex = object()
    constraints = [LocationConstraint(vertex, (0, 0))]
    assert algorithm({vertex: {Cores: 1}}, [], machine, constraints,
                     **kwargs) == {vertex: (0, 0)}

    # Should be able to constrain a single vertex in a large system
    machine = Machine(10, 10)
    vertex = object()
    constraints = [LocationConstraint(vertex, (5, 5))]
    assert algorithm({vertex: {Cores: 1}}, [], machine, constraints,
                     **kwargs) == {vertex: (5, 5)}

    # Should be able to constrain many vertices
    machine = Machine(5, 5)
    manual_placement = {object(): (x, y) for x in range(5) for y in range(5)}
    constraints = [
        LocationConstraint(v, xy) for (v, xy) in iteritems(manual_placement)]
    assert algorithm({v: {Cores: 1} for v in manual_placement},
                     [], machine, constraints, **kwargs) == manual_placement

    # Should be able to mix constrained and unconstrained vertices. As an added
    # detail, in this test the supplied vertices are provided in an interleaved
    # order to ensure that no special ordering is required by the algorithm.
    machine = Machine(4, 1, chip_resources={Cores: 1})
    constrained_vertex_1 = "fixed1"
    constrained_vertex_2 = "fixed2"
    free_vertex_1 = "free1"
    free_vertex_2 = "free2"
    constraints = [LocationConstraint(constrained_vertex_1, (0, 0)),
                   LocationConstraint(constrained_vertex_2, (2, 0))]
    nets = [Net(constrained_vertex_1, free_vertex_1),
            Net(constrained_vertex_2, free_vertex_2)]
    assert algorithm(OrderedDict([(constrained_vertex_1, {Cores: 1}),
                                  (free_vertex_1, {Cores: 1}),
                                  (constrained_vertex_2, {Cores: 1}),
                                  (free_vertex_2, {Cores: 1})]),
                     nets, machine, constraints, **kwargs) \
        in ({constrained_vertex_1: (0, 0),
             constrained_vertex_2: (2, 0),
             free_vertex_1: (1, 0),
             free_vertex_2: (3, 0)},
            {constrained_vertex_1: (0, 0),
             constrained_vertex_2: (2, 0),
             free_vertex_1: (3, 0),
             free_vertex_2: (1, 0)})

    # Should fail placing a vertex onto a dead chip
    machine = Machine(2, 2, dead_chips=set([(0, 0)]))
    vertex = object()
    constraints = [LocationConstraint(vertex, (0, 0))]
    with pytest.raises(InvalidConstraintError):
        algorithm({vertex: {Cores: 1}}, [], machine, constraints, **kwargs)

    # Should fail placing a vertex onto a chip outside the system
    machine = Machine(2, 2)
    vertex = object()
    constraints = [LocationConstraint(vertex, (2, 2))]
    with pytest.raises(InvalidConstraintError):
        algorithm({vertex: {Cores: 1}}, [], machine, constraints, **kwargs)

    # Should fail placing a vertex onto a chip without sufficient resources
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    constraints = [LocationConstraint(vertex, (0, 0))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {Cores: 2}}, [], machine, constraints, **kwargs)


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_reserve_resource_constraint(algorithm, kwargs):
    """Test that the ReserveResourceConstraint is respected."""
    # Should be able to limit resources on every chip to make the situation
    # impossible
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {Cores: 1}}, [], machine, constraints, **kwargs)

    # Should be able to limit resources on every chip making the constraint
    # tortologically impossible.
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1)),
                   ReserveResourceConstraint(Cores, slice(1, 2))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {}}, [], machine, constraints, **kwargs)

    # Should be able to limit resources on every chip making the constraint
    # tortologically impossible on a single chip.
    machine = Machine(2, 1, chip_resources={Cores: 1},
                      chip_resource_exceptions={(0, 0): {Cores: 0}})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {}}, [], machine, constraints, **kwargs)

    # Should be able to limit resources on specific chip to make the situation
    # impossible
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1), (0, 0))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {Cores: 1}}, [], machine, constraints, **kwargs)

    # Should be able to limit resources on a specific chip making the
    # constraint tortologically impossible.
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1), (0, 0)),
                   ReserveResourceConstraint(Cores, slice(1, 2), (0, 0))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {}}, [], machine, constraints, **kwargs)

    # Should be able to limit resources on a specific chip making the
    # constraint tortologically impossible on that chip.
    machine = Machine(2, 1, chip_resources={Cores: 1},
                      chip_resource_exceptions={(0, 0): {Cores: 0}})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1), (0, 0))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {}}, [], machine, constraints, **kwargs)

    # Should be able to limit resources on chips with resource exceptions to
    # make the situation impossible
    machine = Machine(1, 1,
                      chip_resources={Cores: 1},
                      chip_resource_exceptions={(0, 0): {Cores: 1}})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {Cores: 1}}, [], machine, constraints, **kwargs)

    # Should be able to limit resources such that things are spread out
    machine = Machine(2, 2, chip_resources={Cores: 2})
    vertices_resources = {object(): {Cores: 1} for _ in range(4)}
    constraints = [ReserveResourceConstraint(Cores, slice(1, 2))]
    placements = algorithm(vertices_resources, [], machine, constraints,
                           **kwargs)
    used_chips = set()
    for vertex in vertices_resources:
        assert vertex in placements
        assert placements[vertex] not in used_chips
        used_chips.add(placements[vertex])
    assert len(placements) == 4
    assert len(used_chips) == 4


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_same_chip_constraint(algorithm, kwargs):
    """Test that the SameChipConstraint is respected."""
    # Should be able to cause two vertices to be colocated in an impossible
    # manner
    machine = Machine(2, 1, chip_resources={Cores: 1})
    v0 = object()
    v1 = object()
    constraints = [SameChipConstraint([v0, v1])]
    with pytest.raises(InsufficientResourceError):
        algorithm({v0: {Cores: 1}, v1: {Cores: 1}}, [], machine, constraints,
                  **kwargs)

    # Create a number of random networks and make sure that constrained
    # vertices are always placed together (chance would ensure they otherwise
    # would not since nothing particularly will pull them together)
    for _ in range(10):
        machine = Machine(2, 2, chip_resources={Cores: 3})
        vertices = [object() for _ in range(9)]
        vertices_resources = {v: {Cores: 1} for v in vertices}
        nets = [Net(v, random.choice(vertices)) for v in vertices]
        constraints = [SameChipConstraint(vertices[:2])]
        placements = algorithm(vertices_resources, nets, machine, constraints,
                               **kwargs)

        # No extra vertices should have apppeared
        assert set(placements) == set(vertices)

        # The placement of the two constrained vertices should be conincident
        assert placements[vertices[0]] == placements[vertices[1]]

    # Make sure tricky edge-cases are handled correctly by placers:
    # * Overlapping constraints
    # * Singleton constraints
    # * Constraints with repeated vertices
    # * Duplicate constraints
    machine = Machine(2, 2)
    v0 = object()
    v1 = object()
    v2 = object()
    v3 = object()
    vertices_resources = {v: {Cores: 1} for v in [v0, v1, v2, v3]}
    nets = [Net(v0, [v1, v2, v3])]
    constraints = [SameChipConstraint([v0, v1]),  # Overlapping
                   SameChipConstraint([v0, v2]),
                   SameChipConstraint([v2, v3]),
                   SameChipConstraint([v3]),      # Singleton
                   SameChipConstraint([v3]),      # Duplicate
                   SameChipConstraint([v3, v3])]  # Repeated vertex
    placements = algorithm(vertices_resources, nets, machine, constraints,
                           **kwargs)

    # No extra vertices should have apppeared
    assert set(placements) == set([v0, v1, v2, v3])

    # All four vertices should be placed on top each other
    assert len(set(placements.values())) == 1
