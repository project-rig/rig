"""Test utility functions for placers."""

import pytest

from rig.par.place.common import subtract_resources, overallocated


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
