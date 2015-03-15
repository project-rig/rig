"""Generic correctness tests applicable to all placement algorithms."""

import pytest

from six import iteritems

from rig.netlist import Net

from rig.machine import Machine, Cores

from rig.place_and_route.exceptions import InsufficientResourceError
from rig.place_and_route.exceptions import InvalidConstraintError

from rig.place_and_route.constraints import LocationConstraint, \
    ReserveResourceConstraint

from rig.place_and_route import place as default_place
from rig.place_and_route.place.hilbert import place as hilbert_place

# This dictionary should be updated to contain all implemented algorithms along
# with applicable keyword arguments.
ALGORITHMS_UNDER_TEST = [(default_place, {}),
                         (hilbert_place, {})]


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


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_trivial(algorithm, kwargs):
    """Test that algorithms succeed in placing trivial cases.

    Note that these tests are intended to be so easy that it will just weed out
    fundamental failures of placement algorithms. Note that in general,
    however, it is perfectly acceptable for problems to exist which not all
    placers can handle.
    """
    # Putting in just one vertex in a singleton machine.
    machine = Machine(1, 1)
    vertex = object()
    assert algorithm({vertex: {Cores: 1}}, [], machine, [], **kwargs) \
        == {vertex: (0, 0)}

    # Putting in just one vertex into a large machine
    machine = Machine(10, 10)
    vertex = object()
    placement = algorithm({vertex: {Cores: 1}}, [], machine, [], **kwargs)
    assert vertex in placement
    assert placement[vertex] in machine

    # Putting in multiple vertices in a singleton machine with adequate
    # resources.
    machine = Machine(1, 1, chip_resources={Cores: 8})
    vertices = [object() for _ in range(8)]
    assert algorithm({v: {Cores: 1} for v in vertices},  # pragma: no branch
                     [], machine, [], **kwargs) \
        == {v: (0, 0) for v in vertices}

    # Putting in multiple connected vertices in a singleton machine with
    # adequate resources.
    machine = Machine(1, 1, chip_resources={Cores: 8})
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[1:])]
    assert algorithm({v: {Cores: 1} for v in vertices},  # pragma: no branch
                     nets, machine, [], **kwargs) \
        == {v: (0, 0) for v in vertices}

    # Putting in small number of disconnected vertices into a large machine
    # with adequate resources.
    machine = Machine(10, 10, chip_resources={Cores: 1})
    vertices = [object() for _ in range(8)]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          [], machine, [], **kwargs)
    used_chips = set()
    for v in vertices:
        assert v in placement
        assert placement[v] in machine
        assert placement[v] not in used_chips
        used_chips.add(v)

    # Putting in small number of connected vertices into a large machine with
    # adequate resources.
    machine = Machine(10, 10, chip_resources={Cores: 1})
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[1:])]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          nets, machine, [], **kwargs)
    used_chips = set()
    for v in vertices:
        assert v in placement
        assert placement[v] in machine
        assert placement[v] not in used_chips
        used_chips.add(v)

    # Putting in small number of disconnected groups of vertices into a large
    # machine with adequate resources.
    machine = Machine(10, 10, chip_resources={Cores: 1})
    vertices = [object() for _ in range(8)]
    nets = [Net(vertices[0], vertices[1:4]),
            Net(vertices[4], vertices[5:])]
    placement = algorithm({v: {Cores: 1} for v in vertices},
                          nets, machine, [], **kwargs)
    used_chips = set()
    for v in vertices:
        assert v in placement
        assert placement[v] in machine
        assert placement[v] not in used_chips
        used_chips.add(v)


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

    # Should be able to mix constrained and unconstrained vertices
    machine = Machine(2, 1, chip_resources={Cores: 1})
    constrained_vertex = object()
    free_vertex = object()
    constraints = [LocationConstraint(constrained_vertex, (0, 0))]
    assert algorithm({constrained_vertex: {Cores: 1}, free_vertex: {Cores: 1}},
                     [], machine, constraints, **kwargs) \
        == {constrained_vertex: (0, 0), free_vertex: (1, 0)}

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

    # Should be able to limit resources on specific chip to make the situation
    # impossible
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1), (0, 0))]
    with pytest.raises(InsufficientResourceError):
        algorithm({vertex: {Cores: 1}}, [], machine, constraints, **kwargs)

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
