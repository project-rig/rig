"""Common utility functions for placement algorithms."""

from six import iteritems, itervalues

from rig.place_and_route.exceptions import InsufficientResourceError


def add_resources(res_a, res_b):
    """Return the resources after adding res_b's resources to res_a.

    Parameters
    ----------
    res_a : dict
        Dictionary `{resource: value, ...}`.
    res_b : dict
        Dictionary `{resource: value, ...}`. Must be a (non-strict) subset of
        res_a. If A resource is not present in res_b, the value is presumed to
        be 0.
    """
    return {resource: value + res_b.get(resource, 0)
            for resource, value in iteritems(res_a)}


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


def resources_after_reservation(res, constraint):
    """Return the resources available after a specified
    ReserveResourceConstraint has been applied.

    Note: the caller is responsible for testing that the constraint is
    applicable to the core whose resources are being constrained.

    Note: this function does not pay attention to the specific position of the
    reserved regieon, only its magnitude.
    """
    res = res.copy()
    res[constraint.resource] -= (constraint.reservation.stop -
                                 constraint.reservation.start)
    return res


def apply_reserve_resource_constraint(machine, constraint):
    """Apply the changes inplied by a reserve resource constraint to a
    machine model."""
    if constraint.location is None:
        # Compensate for globally reserved resources
        machine.chip_resources \
            = resources_after_reservation(
                machine.chip_resources, constraint)
        if overallocated(machine.chip_resources):
            raise InsufficientResourceError(
                "Cannot meet {}".format(constraint))
        for location in machine.chip_resource_exceptions:
            machine.chip_resource_exceptions[location] \
                = resources_after_reservation(
                    machine.chip_resource_exceptions[location],
                    constraint)
            if overallocated(machine[location]):
                raise InsufficientResourceError(
                    "Cannot meet {}".format(constraint))
    else:
        # Compensate for reserved resources at a specified location
        machine[constraint.location] = resources_after_reservation(
            machine[constraint.location], constraint)
        if overallocated(machine[constraint.location]):
            raise InsufficientResourceError(
                "Cannot meet {}".format(constraint))
