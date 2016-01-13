import pytest

from itertools import cycle

from mock import Mock, call

from six import iteritems, next

from rig.netlist import Net

from rig.place_and_route.machine import Machine, Cores, SDRAM

from rig.place_and_route.place import sa

import random


def test__net_cost_no_wrap():
    """Make sure net costs are calculated correctly."""
    machine = Machine(3, 3)
    l2v = {(x, y): [object() for _ in range(3)]
           for x in range(3) for y in range(3)}
    placements = {}
    for xy, vs in iteritems(l2v):
        for v in vs:
            placements[v] = xy

    # Should report zero cost for a net with no targets
    assert sa._net_cost(Net(l2v[(0, 0)][0], []),
                        placements, False, machine) == 0.0

    # Should report zero cost for a net with targets in the same chip
    assert sa._net_cost(Net(l2v[(0, 0)][0],
                            l2v[(0, 0)][1:]),
                        placements, False, machine) == 0.0

    # Should report cost 1 for a net to a chip one cell away
    assert sa._net_cost(Net(l2v[(1, 1)][0],
                            l2v[(1, 0)][0]),
                        placements, False, machine) == 1.0
    assert sa._net_cost(Net(l2v[(1, 1)][0],
                            l2v[(2, 1)][0]),
                        placements, False, machine) == 1.0

    # Should report cost for a square net
    assert sa._net_cost(Net(l2v[(1, 1)][0],
                            l2v[(2, 2)][0]),
                        placements, False, machine) == 2.0
    assert sa._net_cost(Net(l2v[(0, 0)][0],
                            l2v[(2, 2)][0]),
                        placements, False, machine) == 4.0

    # Should account for the weight
    assert sa._net_cost(Net(l2v[(0, 0)][0],
                            l2v[(2, 2)][0], 0.5),
                        placements, False, machine) == 4.0 / 2.0


def test__net_cost_with_wrap():
    """Make sure net costs are calculated correctly when wrapping."""
    machine = Machine(3, 3)
    l2v = {(x, y): [object() for _ in range(3)]
           for x in range(3) for y in range(3)}
    placements = {}
    for xy, vs in iteritems(l2v):
        for v in vs:
            placements[v] = xy

    # Should report zero cost for a net with no targets
    assert sa._net_cost(Net(l2v[(0, 0)][0], []),
                        placements, True, machine) == 0.0

    # Should report zero cost for a net with targets in the same chip
    assert sa._net_cost(Net(l2v[(0, 0)][0],
                            l2v[(0, 0)][1:]),
                        placements, True, machine) == 0.0

    # Should report cost 1 for a net to a chip one cell away
    assert sa._net_cost(Net(l2v[(1, 1)][0],
                            l2v[(1, 0)][0]),
                        placements, True, machine) == 1.0
    assert sa._net_cost(Net(l2v[(1, 1)][0],
                            l2v[(2, 1)][0]),
                        placements, True, machine) == 1.0
    # ...with wrapping
    assert sa._net_cost(Net(l2v[(2, 2)][0],
                            l2v[(2, 0)][0]),
                        placements, True, machine) == 1.0
    assert sa._net_cost(Net(l2v[(2, 2)][0],
                            l2v[(0, 2)][0]),
                        placements, True, machine) == 1.0

    # Should report cost for a square net
    assert sa._net_cost(Net(l2v[(1, 1)][0],
                            l2v[(2, 2)][0]),
                        placements, True, machine) == 2.0
    assert sa._net_cost(Net(l2v[(0, 0)][0],
                            [l2v[(1, 1)][0], l2v[(2, 2)][0]]),
                        placements, True, machine) == 4.0
    # With wrapping
    assert sa._net_cost(Net(l2v[(0, 0)][0],
                            l2v[(2, 2)][0]),
                        placements, True, machine) == 2.0

    # Should account for the weight
    assert sa._net_cost(Net(l2v[(0, 0)][0],
                            l2v[(2, 2)][0], 0.5),
                        placements, True, machine) == 2.0 / 2.0


@pytest.mark.parametrize("resources,expectation",
                         [({}, []),
                          # Using free resources should work
                          ({SDRAM: 32}, []),
                          ({Cores: 1}, []),
                          ({Cores: 1, SDRAM: 16}, []),
                          # Vertices should be greedily removed left-to-right
                          # to meet a request, skipping fixed vertices
                          ({Cores: 2}, ["v1"]),
                          ({Cores: 3}, ["v1", "v3"]),
                          ({SDRAM: 64}, ["v1", "v3"]),
                          ({SDRAM: 128}, ["v1", "v3", "v4"]),
                          # Requesting more resources than can be freed up
                          # should fail
                          ({Cores: 4}, None),
                          # More resources than are available overall should
                          # fail
                          ({Cores: 5}, None),
                          ({SDRAM: 129}, None)])
def test__get_candidate_swap(resources, expectation):
    machine = Machine(1, 1, chip_resources={Cores: 4, SDRAM: 128})

    v1 = "v1"
    v2 = "v2"
    v3 = "v3"
    v4 = "v4"

    l2v = {(0, 0): [v1, v2, v3, v4]}

    vertices_resources = {
        v1: {Cores: 1},
        v2: {Cores: 1},
        v3: {Cores: 1, SDRAM: 64},
        v4: {SDRAM: 32},
    }
    machine.chip_resource_exceptions = {
        (0, 0): {Cores: 1, SDRAM: 32},
    }

    fixed_vertices = {v2: (0, 0)}

    assert sa._get_candidate_swap(resources,
                                  (0, 0), l2v, vertices_resources,
                                  fixed_vertices, machine) == expectation


def test__swap():
    """Test that the swap function updates all required data structures."""
    machine = Machine(3, 3, {Cores: 7},
                      {(x, y): {Cores: 1}
                       for x in range(3)
                       for y in range(3)})
    l2v = {(x, y): [object() for _ in range(3)]
           for x in range(3) for y in range(3)}

    # At each location, the Nth vertex uses N cores.
    vertices_resources = {}
    for loc, vertices in iteritems(l2v):
        for i, vertex in enumerate(vertices):
            vertices_resources[vertex] = {Cores: i+1}

    placements = {}
    for xy, vs in iteritems(l2v):
        for v in vs:
            placements[v] = xy

    # Create a copy of the initial setup for easy comparison
    machine_ = machine.copy()
    l2v_ = {xy: vs[:] for xy, vs in iteritems(l2v)}
    vertices_resources_ = {v: r.copy()
                           for v, r in iteritems(vertices_resources)}
    placements_ = placements.copy()

    # A null swap should achieve nothing
    sa._swap([], (0, 0), [], (1, 1),
             l2v, vertices_resources, placements, machine)
    assert machine == machine_
    assert l2v == l2v_
    assert vertices_resources == vertices_resources_
    assert placements == placements_

    # Moving a single object should work
    sa._swap([l2v[(0, 0)][0]], (0, 0), [], (1, 1),
             l2v, vertices_resources, placements, machine)
    machine_after_move = machine_.copy()
    machine_after_move[(0, 0)] = {Cores: 2}
    machine_after_move[(1, 1)] = {Cores: 0}
    assert machine == machine_after_move
    l2v_after_move = l2v_.copy()
    l2v_after_move[(0, 0)] = l2v_[(0, 0)][1:]
    l2v_after_move[(1, 1)] = l2v_[(1, 1)] + [l2v_[(0, 0)][0]]
    assert l2v == l2v_after_move
    assert vertices_resources == vertices_resources_
    placements_after_move = placements_.copy()
    placements_after_move[l2v_[(0, 0)][0]] = (1, 1)
    assert placements == placements_after_move

    # Should be able to swap back again (note the re-ordering within the core)
    sa._swap([], (0, 0), [l2v[(1, 1)][-1]], (1, 1),
             l2v, vertices_resources, placements, machine)
    assert machine == machine_
    l2v_after_move = l2v_.copy()
    l2v_after_move[(0, 0)] = l2v_[(0, 0)][1:] + [l2v_[(0, 0)][0]]
    assert l2v == l2v_after_move
    assert vertices_resources == vertices_resources_
    assert placements == placements_

    # Should be able to swap en-mass
    sa._swap(l2v[(1, 2)][:], (1, 2), l2v[(2, 2)][:], (2, 2),
             l2v, vertices_resources, placements, machine)
    assert machine == machine_
    l2v_after_move[(1, 2)] = l2v_[(2, 2)][:]
    l2v_after_move[(2, 2)] = l2v_[(1, 2)][:]
    assert l2v == l2v_after_move
    assert vertices_resources == vertices_resources_
    placements_after_move = placements_.copy()
    for v in l2v_[(1, 2)]:
        placements_after_move[v] = (2, 2)
    for v in l2v_[(2, 2)]:
        placements_after_move[v] = (1, 2)
    assert placements == placements_after_move


@pytest.mark.parametrize("has_wrap_around_links", [True, False])
def test__step_singleton(has_wrap_around_links):
    """Make sure that the step function always fails when there is a singleton
    machine since there is no swap to be made."""
    machine = Machine(1, 1)
    l2v = {(0, 0): [object() for _ in range(3)]}
    vertices_resources = {v: {} for v in l2v[(0, 0)]}
    vertices = list(vertices_resources)
    placements = {v: (0, 0) for v in l2v[(0, 0)]}
    v2n = {}
    fixed_vertices = {}

    # The step is called with a very high temperature meaning that if it did
    # try to swap it would probably be accepted.
    r = random.Random()
    for _ in range(10):
        assert sa._step(vertices, 1, 1.e1000, placements, l2v, v2n,
                        vertices_resources, fixed_vertices, machine,
                        has_wrap_around_links, r) == (False, 0.0)


@pytest.mark.parametrize("has_wrap_around_links", [True, False])
def test__step_not_same_chip_and_rand_range(has_wrap_around_links):
    """Make sure that the step function always chooses a chip which isn't the
    same as the source. Also verifies that random number generator for target
    selection is stimulated correctly."""
    machine = Machine(3, 1)
    l2v = {(0, 0): [object()], (1, 0): [object()]}
    vertices_resources = {v: {} for v in [l2v[(0, 0)][0], l2v[(1, 0)][0]]}
    vertices = list(vertices_resources)
    placements = {l2v[(0, 0)][0]: (0, 0), l2v[(1, 0)][0]: (1, 0)}
    v2n = {v: [] for v in vertices}
    fixed_vertices = {}

    r = random.Random()

    # Hard-code the choice of vertex to swap as the one at (1, 0)
    r.choice = Mock(return_value=l2v[(1, 0)][0])

    # A fake random number generator which generates the sequence 1, 0, 0, 0 so
    # that the initial random choice of swap location is (1, 0) followed by (0,
    # 0). In this test we want to guaruntee that the first result is rejected
    # (since it is the same as the "chosen" source vertex) and that the second
    # one is accepted.
    sequence_iter = iter([1, 0, 0, 0])
    r.randint = Mock(side_effect=lambda a, b: next(sequence_iter))

    # We don't really care what the outcome of the step is in this case
    sa._step(vertices, 1, 1.e1000, placements, l2v, v2n,
             vertices_resources, fixed_vertices, machine,
             has_wrap_around_links, r)

    # Make sure that the random number generator was called correctly
    if has_wrap_around_links:
        # Should be requesting ranges which can wrap-around
        correct_calls = [
            call(0, 2),
            call(-1, 1),
            call(0, 2),
            call(-1, 1),
        ]
    else:
        correct_calls = [
            # Should be requesting ranges which are clamped within the system
            call(0, 2),
            call(0, 0),
            call(0, 2),
            call(0, 0),
        ]
    r.randint.assert_has_calls(correct_calls, any_order=False)


@pytest.mark.parametrize("has_wrap_around_links", [True, False])
def test__step_dest_not_dead(has_wrap_around_links):
    """Make sure that the step function always fails when the selected
    target chip is dead."""
    machine = Machine(3, 1, dead_chips=set([(2, 0)]))
    l2v = {(0, 0): [object()], (1, 0): [object()]}
    vertices_resources = {v: {} for v in [l2v[(0, 0)][0], l2v[(1, 0)][0]]}
    vertices = list(vertices_resources)
    placements = {l2v[(0, 0)][0]: (0, 0), l2v[(1, 0)][0]: (1, 0)}
    v2n = {v: [] for v in vertices}
    fixed_vertices = {}

    r = random.Random()

    # Hard-code the choice of vertex to swap as the one at (1, 0)
    r.choice = Mock(return_value=l2v[(1, 0)][0])

    # Generate a sequence of numbers such that (2, 0) is always chosen (which
    # is a dead chip)
    sequence_iter = iter(cycle([2, 0]))
    r.randint = Mock(side_effect=lambda a, b: next(sequence_iter))

    # We simply make sure that this reliably doesn't produce a swap
    for _ in range(10):
        assert sa._step(vertices, 1, 1.e1000, placements, l2v, v2n,
                        vertices_resources, fixed_vertices, machine,
                        has_wrap_around_links, r) == (False, 0.0)


@pytest.mark.parametrize("has_wrap_around_links", [True, False])
def test__step_dest_too_small(has_wrap_around_links):
    """Make sure that the step function always fails when the selected
    target chip is too small."""
    machine = Machine(2, 1, {Cores: 2}, {(0, 0): {Cores: 1},
                                         (1, 0): {Cores: 0}})
    l2v = {(0, 0): [], (1, 0): [object()]}
    vertices_resources = {l2v[(1, 0)][0]: {Cores: 2}}
    vertices = list(vertices_resources)
    placements = {l2v[(1, 0)][0]: (1, 0)}
    v2n = {v: [] for v in vertices}
    fixed_vertices = {}

    r = random.Random()

    # Hard-code the choice of vertex to swap as the one at (1, 0)
    r.choice = Mock(return_value=l2v[(1, 0)][0])

    # Generate a sequence of numbers such that (0, 0) is always chosen (which
    # is a chip which doesn't have enough resources to fit the swap)
    sequence_iter = iter(cycle([0, 0]))
    r.randint = Mock(side_effect=lambda a, b: next(sequence_iter))

    # We simply make sure that this reliably doesn't produce a swap
    for _ in range(10):
        assert sa._step(vertices, 1, 1.e1000, placements, l2v, v2n,
                        vertices_resources, fixed_vertices, machine,
                        has_wrap_around_links, r) == (False, 0.0)


@pytest.mark.parametrize("has_wrap_around_links", [True, False])
def test__step_swap_too_large(has_wrap_around_links):
    """Make sure that the step function always fails when the swap made with the
    destination does not fit in the space left at the source."""
    machine = Machine(2, 1, {Cores: 2}, {(0, 0): {Cores: 0},
                                         (1, 0): {Cores: 0}})
    l2v = {(0, 0): [object()], (1, 0): [object()]}
    vertices_resources = {l2v[(0, 0)][0]: {Cores: 2},
                          l2v[(1, 0)][0]: {Cores: 1}}
    vertices = list(vertices_resources)
    placements = {l2v[(0, 0)][0]: (0, 0), l2v[(1, 0)][0]: (1, 0)}
    v2n = {v: [] for v in vertices}
    fixed_vertices = {}

    r = random.Random()

    # Hard-code the choice of vertex to swap as the one at (1, 0)
    r.choice = Mock(return_value=l2v[(1, 0)][0])

    # Generate a sequence of numbers such that (0, 0) is always chosen (which
    # is a chip whose only vertex is larger than the space available in (1, 0)
    # once the swap has been made
    sequence_iter = iter(cycle([0, 0]))
    r.randint = Mock(side_effect=lambda a, b: next(sequence_iter))

    # We simply make sure that this reliably doesn't produce a swap
    for _ in range(10):
        assert sa._step(vertices, 1, 1.e1000, placements, l2v, v2n,
                        vertices_resources, fixed_vertices, machine,
                        has_wrap_around_links, r) == (False, 0.0)


@pytest.mark.parametrize("return_value,should_terminate",
                         [(None, False),
                          (123, False),
                          (0, False),
                          ("hi", False),
                          ("", False),
                          ([0], False),
                          ([], False),
                          (True, False),
                          (False, True)])
def test_callback(return_value, should_terminate):
    """Ensure that a callback function can be registered and can control the
    placement process."""
    vertices = [object() for _ in range(4)]
    vertices_resources = {v: {Cores: 1} for v in vertices}
    nets = [Net(vertices[i], vertices[(i+1) % 4])
            for i in range(4)]
    machine = Machine(4, 1, {Cores: 1})

    cb = Mock(return_value=return_value)

    r = random.Random()
    r.seed(1)
    sa.place(vertices_resources, nets, machine, [],
             on_temperature_change=cb, random=r)

    if should_terminate:
        assert len(cb.mock_calls) == 1
    else:
        assert len(cb.mock_calls) > 1
