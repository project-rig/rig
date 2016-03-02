import pytest

from mock import Mock

from collections import OrderedDict

from six import itervalues

import random

from rig.place_and_route import Machine, Cores
from rig.place_and_route.constraints import \
    LocationConstraint, SameChipConstraint

from rig.netlist import Net

from rig.place_and_route.place.sa import place


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
    placement process. In addition, make sure that the placement info given to
    the callback doesn't include any "False" vertices, e.g. due to the
    SameChipConstraint.
    """
    # We have 10 vertices, the first two of which are constrained to be on the
    # same chip. To avoid packing problems in this test, the two same-chip'd
    # vertices have 1 core each (for a total of 2 cores) and the rest of the
    # vertices have 2 cores each.
    vertices = [object() for _ in range(10)]
    vertices_resources = OrderedDict((v, {Cores: 1 if i < 2 else 2})
                                     for i, v in enumerate(vertices))
    nets = [Net(vertices[i], vertices[(i+1) % len(vertices)])
            for i in range(4)]
    machine = Machine(4, 4, {Cores: 3})
    constraints = [SameChipConstraint(vertices[:2])]

    def fn(iteration_count, placements, current_cost, r_accept,
           temperature, distance_limit):
        assert set(placements) == set(vertices)
        return return_value
    cb = Mock(side_effect=fn)

    r = random.Random()
    r.seed(1)
    place(vertices_resources, nets, machine, constraints,
          on_temperature_change=cb, random=r)

    if should_terminate:
        assert len(cb.mock_calls) == 1
    else:
        assert len(cb.mock_calls) > 1


def test_trivial_case_no_resources():
    """The kernel should not be used when no resources can be consumed (and all
    vertices should be placed on the same chip.
    """
    vertices = [object() for _ in range(10)]
    vertices_resources = {v: {} for v in vertices}
    nets = [Net(vertices[0], vertices)]
    machine = Machine(2, 2, {})
    constraints = []

    kernel = Mock()
    placements = place(vertices_resources, nets, machine, constraints,
                       kernel=kernel)

    # The kernel should not have been used
    assert not kernel.called

    # All vertices should be on the same chip
    chip = placements[vertices[0]]
    assert all(placement == chip for placement in itervalues(placements))


def test_trivial_case_1x1_machine():
    """The kernel should not be used when there is only one chip..."""
    v0 = object()
    v1 = object()
    vertices_resources = {v0: {Cores: 1}, v1: {Cores: 1}}
    nets = [Net(v0, v1)]
    machine = Machine(1, 1, {Cores: 2})
    constraints = []

    kernel = Mock()
    place(vertices_resources, nets, machine, constraints, kernel=kernel)
    assert not kernel.called


def test_trivial_case_no_movable_vertices():
    """The kernel should not be used when no movable vertices are provided."""
    v0 = object()
    v1 = object()
    vertices_resources = {v0: {Cores: 1}, v1: {Cores: 1}}
    nets = [Net(v0, v1)]
    machine = Machine(2, 2, {Cores: 1})
    constraints = [
        LocationConstraint(v0, (0, 0)),
        LocationConstraint(v1, (1, 1)),
    ]

    kernel = Mock()
    place(vertices_resources, nets, machine, constraints, kernel=kernel)
    assert not kernel.called


def test_trivial_case_no_non_zero_weight_nets():
    """The kernel should not be used when no nets have a weight above 0."""
    v0 = object()
    v1 = object()
    vertices_resources = {v0: {Cores: 1}, v1: {Cores: 1}}
    nets = [Net(v0, v1, weight=0.0)]
    machine = Machine(2, 2, {Cores: 1})
    constraints = []

    kernel = Mock()
    place(vertices_resources, nets, machine, constraints, kernel=kernel)
    assert not kernel.called


def test_trivial_case_no_nets_with_two_or_more_vertices():
    """The kernel should not be used when no nets have more than 2 vertices."""
    v0 = object()
    v1 = object()
    vertices_resources = {v0: {Cores: 1}, v1: {Cores: 1}}
    nets = [Net(v0, v0), Net(v1, [])]
    machine = Machine(2, 2, {Cores: 1})
    constraints = []

    kernel = Mock()
    place(vertices_resources, nets, machine, constraints, kernel=kernel)
    assert not kernel.called
