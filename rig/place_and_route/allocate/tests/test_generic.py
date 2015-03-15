"""Generic correctness tests applicable to all allocation algorithms."""

import pytest

from rig.machine import Machine, Cores, SDRAM

from rig.routing_table import Routes

from rig.place_and_route.constraints import \
    ReserveResourceConstraint, AlignResourceConstraint, RouteEndpointConstraint

from rig.place_and_route.exceptions import InsufficientResourceError

from rig.place_and_route import allocate as default_allocate
from rig.place_and_route.allocate.greedy import allocate as greedy_allocate

# This dictionary should be updated to contain all implemented algorithms along
# with applicable keyword arguments.
ALGORITHMS_UNDER_TEST = [(default_allocate, {}),
                         (greedy_allocate, {})]


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_null_allocation(algorithm, kwargs):
    """Test algorithms correctly handle cases where no resources need
    allocating.
    """
    # Test with a non-null machine
    machine = Machine(2, 2, chip_resources={})
    vertices_resources = {object(): {} for _ in range(4)}
    placements = {v: (i % 2, i//2) for i, v in enumerate(vertices_resources)}
    assert algorithm(vertices_resources,  # pragma: no branch
                     [], machine, [], placements,
                     **kwargs) \
        == {v: {} for v in vertices_resources}

    # Test with a null machine
    machine = Machine(0, 0, chip_resources={})
    assert algorithm({}, [], machine, [], {}, **kwargs) == {}


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
@pytest.mark.parametrize("constraints",
                         ([], [RouteEndpointConstraint(None, Routes.north)]))
def test_allocation(algorithm, kwargs, constraints):
    """Test allocating non-empty sets of vertices and with irellevant
    constraints."""
    # Test single vertex with a single allocation which should exactly fit
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    vertices_resources = {vertex: {Cores: 1}}
    placements = {vertex: (0, 0)}
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {vertex: {Cores: slice(0, 1)}}

    # Test single vertex with a single large allocation which should exactly
    # fit
    machine = Machine(1, 1, chip_resources={SDRAM: 128})
    vertex = object()
    vertices_resources = {vertex: {SDRAM: 128}}
    placements = {vertex: (0, 0)}
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {vertex: {SDRAM: slice(0, 128)}}

    # Test vertex with an allocation of one resource (of a possible many)
    machine = Machine(1, 1, chip_resources={Cores: 1, SDRAM: 128})
    vertex = object()
    vertices_resources = {vertex: {Cores: 1}}
    placements = {vertex: (0, 0)}
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {vertex: {Cores: slice(0, 1)}}

    # Test vertex with an allocation of several resources
    machine = Machine(1, 1, chip_resources={Cores: 1, SDRAM: 128})
    vertex = object()
    vertices_resources = {vertex: {Cores: 1, SDRAM: 128}}
    placements = {vertex: (0, 0)}
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {vertex: {Cores: slice(0, 1), SDRAM: slice(0, 128)}}

    # Test two vertices with a allocations of independent resources on the same
    # chip
    machine = Machine(1, 1, chip_resources={Cores: 1, SDRAM: 128})
    core_vertex = object()
    sdram_vertex = object()
    vertices_resources = {core_vertex: {Cores: 1}, sdram_vertex: {SDRAM: 128}}
    placements = {core_vertex: (0, 0), sdram_vertex: (0, 0)}
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {core_vertex: {Cores: slice(0, 1)},
            sdram_vertex: {SDRAM: slice(0, 128)}}

    # Test two vertices with a allocations on separate chips
    machine = Machine(2, 1, chip_resources={Cores: 1})
    first_vertex = object()
    second_vertex = object()
    vertices_resources = {first_vertex: {Cores: 1}, second_vertex: {Cores: 1}}
    placements = {first_vertex: (0, 0), second_vertex: (1, 0)}
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {first_vertex: {Cores: slice(0, 1)},
            second_vertex: {Cores: slice(0, 1)}}

    # Test multiple vertices which allocate single resources on the same chip
    num = 10
    machine = Machine(1, 1, chip_resources={Cores: num})
    vertices_resources = {object(): {Cores: 1} for _ in range(num)}
    placements = {v: (0, 0) for v in vertices_resources}
    allocation = algorithm(vertices_resources, [], machine, constraints,
                           placements, **kwargs)
    core_allocations = [False]*num
    for vertex in vertices_resources:
        assert vertex in allocation
        assert Cores in allocation[vertex]
        assert len(allocation[vertex]) == 1, "Only has Cores key"
        core_allocation = allocation[vertex][Cores]
        assert core_allocation.step is None
        assert core_allocation.start is not None
        assert core_allocation.stop is not None
        for core in range(core_allocation.start,
                          core_allocation.stop):
            assert 0 <= core < num
            assert core_allocations[core] is False
            core_allocations[core] = True
    assert all(core_allocations)
    assert len(allocation) == num


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_reserve_resource_constraint(algorithm, kwargs):
    """Test adherence to ReserveResourceConstraint constraints."""
    # Test single vertex with a single allocation which should exactly fit in
    # space remaining after the constraint.
    machine = Machine(1, 1, chip_resources={Cores: 2})
    vertex = object()
    vertices_resources = {vertex: {Cores: 1}}
    placements = {vertex: (0, 0)}
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1))]
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {vertex: {Cores: slice(1, 2)}}

    # Test single vertex with a single allocation which should exactly fit in
    # space remaining after the local constraint.
    machine = Machine(1, 1, chip_resources={Cores: 2})
    vertex = object()
    vertices_resources = {vertex: {Cores: 1}}
    placements = {vertex: (0, 0)}
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1), (0, 0))]
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {vertex: {Cores: slice(1, 2)}}

    # Test single vertex with a single slot and a null constraint
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    vertices_resources = {vertex: {Cores: 1}}
    placements = {vertex: (0, 0)}
    constraints = [ReserveResourceConstraint(Cores, slice(0, 0))]
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) == {vertex: {Cores: slice(0, 1)}}

    # Test single vertex with a single slot used up by a constraint fails
    machine = Machine(1, 1, chip_resources={Cores: 1})
    vertex = object()
    vertices_resources = {vertex: {Cores: 1}}
    placements = {vertex: (0, 0)}
    constraints = [ReserveResourceConstraint(Cores, slice(0, 1))]
    with pytest.raises(InsufficientResourceError):
        algorithm(vertices_resources, [], machine, constraints, placements,
                  **kwargs)

    # Test multiple reservations forcing an allocation into a specific gap
    machine = Machine(1, 1, chip_resources={Cores: 13})
    vertex = object()
    vertices_resources = {vertex: {Cores: 3}}
    placements = {vertex: (0, 0)}
    constraints = [ReserveResourceConstraint(Cores, slice(2, 5)),
                   ReserveResourceConstraint(Cores, slice(7, 10))]
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) == {vertex: {Cores: slice(10, 13)}}


@pytest.mark.parametrize("algorithm,kwargs", ALGORITHMS_UNDER_TEST)
def test_align_resource_constraint(algorithm, kwargs):
    """Test adherence to AlignResourceConstraint constraints."""
    # Test a single vertex gets assigned into the only aligned spot
    machine = Machine(1, 1, chip_resources={SDRAM: 4})
    vertex = object()
    vertices_resources = {vertex: {SDRAM: 1}}
    placements = {vertex: (0, 0)}
    constraints = [AlignResourceConstraint(SDRAM, 4)]
    assert algorithm(vertices_resources, [], machine, constraints, placements,
                     **kwargs) \
        == {vertex: {SDRAM: slice(0, 1)}}

    # Test multiple vertices get placed on aligned spots when there is exactly
    # enough room
    num = 10
    alignment = 4
    machine = Machine(1, 1, chip_resources={SDRAM: num*alignment})
    vertices_resources = {object(): {SDRAM: 1} for _ in range(num)}
    placements = {v: (0, 0) for v in vertices_resources}
    constraints = [AlignResourceConstraint(SDRAM, alignment)]
    assignments = algorithm(vertices_resources, [], machine, constraints,
                            placements, **kwargs)
    used_locations = set()
    for vertex in vertices_resources:
        assert vertex in assignments
        assert SDRAM in assignments[vertex]
        assert len(assignments[vertex]) == 1
        assert assignments[vertex][SDRAM].start % alignment == 0
        assert assignments[vertex][SDRAM].start not in used_locations
        used_locations.add(assignments[vertex][SDRAM].start)
    assert len(assignments) == num
    assert len(used_locations) == num

    # Test we run out of space when alignment forces us past free space.
    machine = Machine(1, 1, chip_resources={SDRAM: 4})
    vertices_resources = {object(): {SDRAM: 1} for _ in range(2)}
    placements = {v: (0, 0) for v in vertices_resources}
    constraints = [AlignResourceConstraint(SDRAM, 4)]
    with pytest.raises(InsufficientResourceError):
        algorithm(vertices_resources, [], machine, constraints, placements,
                  **kwargs)
