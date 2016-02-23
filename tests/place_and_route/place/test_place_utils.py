"""Test utility functions for placers."""

import pytest

from rig.place_and_route.machine import Machine, Cores, SDRAM

from rig.netlist import Net

from rig.routing_table import Routes

from rig.place_and_route.exceptions import InsufficientResourceError

from rig.place_and_route.constraints import \
    LocationConstraint, ReserveResourceConstraint, SameChipConstraint, \
    RouteEndpointConstraint

from rig.place_and_route.place.utils import \
    add_resources, subtract_resources, overallocated, \
    resources_after_reservation, apply_reserve_resource_constraint, \
    MergedVertex, apply_same_chip_constraints, finalise_same_chip_constraints


def test_add_resources():
    # Null-case
    assert add_resources({}, {}) == {}

    # Adding nothing to something
    assert add_resources({"a": 0, "b": 0}, {}) == {"a": 0, "b": 0}

    # Adding subset of zeros to something
    assert add_resources({"a": 0, "b": 0}, {"a": 0}) \
        == {"a": 0, "b": 0}

    # Adding zeros to something
    assert add_resources({"a": 0, "b": 0}, {"a": 0, "b": 0}) \
        == {"a": 0, "b": 0}

    # Adding subset of non-zeros to something
    assert add_resources({"a": 10, "b": 20}, {"a": 1}) \
        == {"a": 11, "b": 20}

    # Adding non-zeros to something
    assert add_resources({"a": 10, "b": 20}, {"a": 1, "b": 2}) \
        == {"a": 11, "b": 22}


def test_subtract_resources():
    # Null-case
    assert subtract_resources({}, {}) == {}

    # Subtracting nothing from something
    assert subtract_resources({"a": 0, "b": 0}, {}) == {"a": 0, "b": 0}

    # Subtracting subset of zeros from something
    assert subtract_resources({"a": 0, "b": 0}, {"a": 0}) \
        == {"a": 0, "b": 0}

    # Subtracting zeros from something
    assert subtract_resources({"a": 0, "b": 0}, {"a": 0, "b": 0}) \
        == {"a": 0, "b": 0}

    # Subtracting subset of non-zeros from something
    assert subtract_resources({"a": 10, "b": 20}, {"a": 1}) \
        == {"a": 9, "b": 20}

    # Subtracting non-zeros from something
    assert subtract_resources({"a": 10, "b": 20}, {"a": 1, "b": 2}) \
        == {"a": 9, "b": 18}


def test_overallocated():
    # Null case
    assert not overallocated({})

    # Singletons
    assert not overallocated({"a": 0})
    assert not overallocated({"a": 10})
    assert overallocated({"a": -1})

    # Multiple
    assert not overallocated({"a": 0, "b": 0})
    assert not overallocated({"a": 1, "b": 1})
    assert overallocated({"a": -1, "b": 1})
    assert overallocated({"a": -1, "b": 0})
    assert overallocated({"a": -1, "b": -1})


def test_unreserved_resources():
    # Null constraint
    constraint = ReserveResourceConstraint(Cores, slice(0, 0))
    assert resources_after_reservation({Cores: 0}, constraint) == {Cores: 0}

    # Constrain some away
    constraint = ReserveResourceConstraint(Cores, slice(0, 1))
    assert resources_after_reservation({Cores: 10}, constraint) == {Cores: 9}

    # Non-zero starting point of reservation
    constraint = ReserveResourceConstraint(Cores, slice(9, 10))
    assert resources_after_reservation({Cores: 10}, constraint) == {Cores: 9}

    # Constrain everything away
    constraint = ReserveResourceConstraint(Cores, slice(0, 10))
    assert resources_after_reservation({Cores: 10}, constraint) == {Cores: 0}


def test_apply_reserve_resource_constraint():
    machine = Machine(2, 1, {Cores: 3}, {(0, 0): {Cores: 1}})
    machine_ = machine.copy()

    # Null constraint changes nothing
    constraint = ReserveResourceConstraint(Cores, slice(0, 0))
    apply_reserve_resource_constraint(machine, constraint)
    assert machine == machine_

    # Global constraint changes global resources and resource exceptions
    constraint = ReserveResourceConstraint(Cores, slice(0, 1))
    apply_reserve_resource_constraint(machine, constraint)
    assert machine == Machine(2, 1, {Cores: 2}, {(0, 0): {Cores: 0}})
    machine = machine_.copy()

    # Local constraint only modifes exceptions
    constraint = ReserveResourceConstraint(Cores, slice(0, 1), (0, 0))
    apply_reserve_resource_constraint(machine, constraint)
    assert machine == Machine(2, 1, {Cores: 3}, {(0, 0): {Cores: 0}})
    machine = machine_.copy()

    constraint = ReserveResourceConstraint(Cores, slice(0, 1), (1, 0))
    apply_reserve_resource_constraint(machine, constraint)
    assert machine == Machine(2, 1, {Cores: 3},
                              {(0, 0): {Cores: 1}, (1, 0): {Cores: 2}})
    machine = machine_.copy()

    # Globally tortologically impossible constraints should fail
    constraint = ReserveResourceConstraint(Cores, slice(0, 4))
    with pytest.raises(InsufficientResourceError):
        apply_reserve_resource_constraint(machine, constraint)
    machine = machine_.copy()

    # Globally tortologically impossible constraints should fail when the
    # failiure is only due to an exception
    constraint = ReserveResourceConstraint(Cores, slice(0, 2))
    with pytest.raises(InsufficientResourceError):
        apply_reserve_resource_constraint(machine, constraint)
    machine = machine_.copy()

    # Local tortologically impossible constraints should fail
    constraint = ReserveResourceConstraint(Cores, slice(0, 2), (0, 0))
    with pytest.raises(InsufficientResourceError):
        apply_reserve_resource_constraint(machine, constraint)
    machine = machine_.copy()


class TestApplySameChipConstraints(object):
    """Tests for the apply_same_chip_constraints function and friends."""

    @pytest.mark.parametrize("vertices_resources,nets",
                             [({}, []),
                              ({"v0": {Cores: 1}}, [Net("v0", "v0")])])
    @pytest.mark.parametrize("constraints",
                             [[],
                              [ReserveResourceConstraint(Cores, slice(0, 1))]])
    def test_null(self, vertices_resources, nets, constraints):
        # Should do nothing except copy the input when no constraints are given
        vr_out, n_out, c_out, substitutions = apply_same_chip_constraints(
            vertices_resources, nets, constraints)
        assert vr_out == vertices_resources
        assert n_out == nets
        assert c_out == constraints
        assert substitutions == []

    def test_substitute(self):
        # In this test we attempt to apply the constraint when we supply four
        # SameChipConstraints:
        # * One which is empty (shouldn't change anything, nor fail!)
        # * One which contains just v0 which shouldn't change anything
        # * One which constrains v0 and v1 together
        # * One which constrains v1 and v2 together (and contains a duplicate)
        # * Two constraints which have an intersection of two vertices.
        v0 = object()
        v1 = object()
        v2 = object()
        v3 = object()
        v4 = object()
        v5 = object()
        v6 = object()
        v7 = object()
        vertices_resources = {
            v0: {Cores: 1},
            v1: {Cores: 2, SDRAM: 4},
            v2: {SDRAM: 8},
            v3: {Cores: 16, SDRAM: 32},
            v4: {Cores: 1},
            v5: {Cores: 1},
            v6: {Cores: 1},
            v7: {Cores: 1},
        }
        nets = [
            Net(v0, [v0, v1, v2, v3], 123),
            Net(v1, v2, 456),
            Net(v3, v0, 789),
        ]
        constraints = [
            # The SameChipConstraints under test
            SameChipConstraint([]),
            SameChipConstraint([v0]),
            SameChipConstraint([v0, v1]),
            SameChipConstraint([v1, v2, v2]),  # NB: Duplicate v2
            SameChipConstraint([v4, v5, v6]),
            SameChipConstraint([v5, v6, v7]),

            # One should be modified due to the SameChipConstraint, the other
            # should not.
            LocationConstraint(v0, (1, 2)),
            LocationConstraint(v3, (3, 4)),

            # One should be modified due to the SameChipConstraint, the other
            # should not.
            RouteEndpointConstraint(v2, Routes.north),
            RouteEndpointConstraint(v3, Routes.south),

            # This should not be touched
            ReserveResourceConstraint(Cores, slice(0, 1)),
        ]

        # Should do nothing except copy the input when no constraints are given
        vr_out, n_out, c_out, substitutions = apply_same_chip_constraints(
            vertices_resources, nets, constraints)

        # Should have a substitution only for the four constraints which
        # actually achieve anything
        assert len(substitutions) == 4
        assert substitutions[0].vertices == [v0, v1]
        assert substitutions[1].vertices == [substitutions[0], v2, v2]
        assert substitutions[2].vertices == [v4, v5, v6]
        assert substitutions[3].vertices == [
            substitutions[2], substitutions[2], v7]

        # The vertex used for the merged vertices
        vm1 = substitutions[1]
        vm2 = substitutions[3]

        # The merged vertices should have their resources combined
        assert vr_out == {
            vm1: {Cores: 3, SDRAM: 12},
            vm2: {Cores: 4},
            v3: {Cores: 16, SDRAM: 32},
        }

        # The nets should be the same as those supplied except with merged
        # vertices substituted in
        assert len(n_out) == len(nets)

        assert n_out[0].source == vm1
        assert n_out[0].sinks == [vm1, vm1, vm1, v3]
        assert n_out[0].weight == 123

        assert n_out[1].source == vm1
        assert n_out[1].sinks == [vm1]
        assert n_out[1].weight == 456

        assert n_out[2].source == v3
        assert n_out[2].sinks == [vm1]
        assert n_out[2].weight == 789

        # The constraints should be updated accordingly
        assert len(c_out) == len(constraints)
        assert c_out[0].vertices == []
        assert c_out[1].vertices == [vm1]
        assert c_out[2].vertices == [vm1, vm1]
        assert c_out[3].vertices == [vm1, vm1, vm1]

        assert c_out[4].vertices == [vm2, vm2, vm2]
        assert c_out[5].vertices == [vm2, vm2, vm2]

        assert c_out[6].vertex == vm1
        assert c_out[6].location == (1, 2)

        assert c_out[7].vertex == v3
        assert c_out[7].location == (3, 4)

        assert c_out[8].vertex == vm1
        assert c_out[8].route == Routes.north

        assert c_out[9].vertex == v3
        assert c_out[9].route == Routes.south

        assert c_out[10] is constraints[10]


class TestFinaliseSameChipConstraints(object):
    """Tests for the finalise_same_chip_constraints function."""

    def test_null(self):
        # Test that the finalise_same_chip_constraints works when there's
        # nothing to do...
        v0 = object()
        v1 = object()
        v2 = object()
        v3 = object()
        placements = {
            v0: (0, 1),
            v1: (1, 2),
            v2: (2, 3),
            v3: (3, 4),
        }
        orig_placements = placements.copy()

        finalise_same_chip_constraints([], placements)

        # Should be no change!
        assert orig_placements == placements

    def test_multiple(self):
        # Test that the finalise_same_chip_constraints works when there's
        # several overlapping substitutions to be made and some duplicates in
        # the expansion list
        v0 = object()
        v1 = object()
        v2 = object()
        v3 = object()
        m0 = MergedVertex([v0, v1])
        m1 = MergedVertex([m0, v2, v2])  # NB: Duplicate

        placements = {
            m1: (0, 1),
            v3: (1, 2),
        }

        finalise_same_chip_constraints([m0, m1], placements)

        # Should have unpacked one after the other (note in reverse order) and
        # no merged vertices should remain.
        assert placements == {
            v0: (0, 1),
            v1: (0, 1),
            v2: (0, 1),
            v3: (1, 2),
        }
