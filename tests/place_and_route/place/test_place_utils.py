"""Test utility functions for placers."""

import pytest

from rig.machine import Machine, Cores

from rig.place_and_route.exceptions import InsufficientResourceError

from rig.place_and_route.constraints import ReserveResourceConstraint

from rig.place_and_route.place.utils import \
    add_resources, subtract_resources, overallocated, \
    resources_after_reservation, apply_reserve_resource_constraint


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
