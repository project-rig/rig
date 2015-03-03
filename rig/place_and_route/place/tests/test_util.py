"""Test utility functions for placers."""

from rig.machine import Cores

from rig.place_and_route.constraints import ReserveResourceConstraint

from rig.place_and_route.place.util import \
    subtract_resources, overallocated, resources_after_reservation


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
