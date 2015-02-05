"""Common utility functions for placement algorithms."""

from six import iteritems, itervalues


def subtract_resources(res_a, res_b):
    """Return the resources remaining after subtracting res_b's resources from
    res_a.

    Parameters
    ----------
    res_a : dict
        Dictionary `{resource: value, ...}`.
    res_b : dict
        Dictionary `{resource: value, ...}`. Must be a (non-strict) subset of
        res_a. If A resource is not present in res_b, the value is presumed to
        be 0.
    """
    return {resource: value - res_b.get(resource, 0)
            for resource, value in iteritems(res_a)}


def overallocated(res):
    """Returns true if any resource has a negative value.
    """
    return any(v < 0 for v in itervalues(res))
