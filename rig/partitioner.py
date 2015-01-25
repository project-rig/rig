"""Partitioning primitives."""
import math


class PartitioningFailedError(Exception):
    """Raised when it was not possible to partition an object."""


def partition(obj, constraints=list()):
    """Partition an object to meet given constraints.

    Parameters
    ----------
    obj :
        An object that consists of atoms that is understood by the given
        constraints.
    constraints : list
        A list of objects obeying the :py:class:`~.Constraint` API.

    Returns
    -------
    list
        A list of :py:func:`slice` objects indicating the slices of the
        original `obj` that will meet the constraints.

    Note
    ----
    Conflicting constraints (e.g., decreasing x increases y) will not work with
    this partitioner.

    Raises
    ------
    PartitioningFailedError
        If partitioning the object fails.
    """
    # Create an initial list of slices to try
    initial_slice = slice(0, obj.n_atoms)
    partitions = [initial_slice]

    # While there exists a slice that exceeds any constraint partition further.
    i = 0
    while any(c(obj, sl) > 1 for c in constraints for sl in partitions):
        # Determine how many splits to make
        n_partitions = max(c(obj, initial_slice) for c in constraints) + i

        # If this is more than the number of atoms we should die
        if n_partitions > obj.n_atoms:
            raise PartitioningFailedError(
                "Could not partition object {}.".format(obj))

        # Make the splits, and increase the number of splits that will be made
        # in the future.
        partitions = split_slice(initial_slice, n_partitions)
        i += 1  # This is nasty but will suffice for most problems

    # Now that partitioning is done we return the slices that we created
    return partitions


class Constraint(object):
    """A constraint represents the maximum utilisation that may be made of a
    resource.
    """
    def __init__(self, max, target=1.0):
        """Create a new constraint.

        Parameters
        ----------
        max : float or int
            The maximum amount of the resource that may be used by a slice of
            an object.
        target : float
            A fiddle factor that may be applied to account for incorrect
            calculation of the resource usage.  This will usually be 0.0 <=
            target <= 1.0.
        """
        self.max = max
        self.target = target

    def __call__(self, obj, obj_slice):
        """Get the number of cuts that must be made for this slice of the
        object to fit within the constraint.

        Parameters
        ----------
        obj :
            An object that is to be partitioned.
        obj_slice : :py:func:`slice`
            A slice object indicating which atoms should be considered.

        Returns
        -------
        int
            An integral number of pieces that the object must be separated into
            to fit the constraint.  `1` means that the slice meets the
            constraints.
        """
        return int(math.ceil(
            self.get_usage(obj, obj_slice) / (self.target*self.max)
        ))

    def get_usage(self, obj, obj_slice):
        """Get the resource usage for a given slice of a given object.

        Parameters
        ----------
        obj :
            An object that is to be partitioned.
        obj_slice : :py:func:`slice`
            A slice object indicating which atoms should be considered.

        Returns
        -------
        float or int
            The current usage in the same units as `max`.

        Notes
        -----
        Override this method to create a custom constraint using
        :py:class:`~rig.partitioner.Constraint`.
        """
        raise NotImplementedError


def split_slice(obj_slice, splits):
    """Create a list of slices by splitting a given slice.

    Parameters
    ----------
    obj_slice : :py:func:`slice`
    splits : int
        Number of slices to generate from `obj_slice`

    Returns
    -------
    list
        A list of `splits` :py:func:`slice` objects that cover the same range
        as `obj_slice`.

    Raises
    ------
    ValueError
        If the given slice is invalid (starts/stops at None, contains a step
        value other than 1 or is negative), or if the number of splits is
        invalid.
    """
    # Check the slice
    if obj_slice.step != 1 and obj_slice.step is not None:
        raise ValueError(
            "obj_slice.step: {}: must be 1 or None".format(obj_slice.step))

    # Check the range of the slice
    if obj_slice.start is None or obj_slice.start < 0:
        raise ValueError("obj_slice.start: {}: must be a positive integer."
                         .format(obj_slice.start))

    if obj_slice.stop is None or obj_slice.stop < 0:
        raise ValueError("obj_slice.stop: {}: must be a positive integer."
                         .format(obj_slice.stop))

    if not obj_slice.start < obj_slice.stop:
        raise ValueError("obj_slice.start ({}) must be strictly less than "
                         "obj_slice.stop ({})".format(
                             obj_slice.start, obj_slice.stop))

    # Check the number of splits
    if not isinstance(splits, int) or splits < 1:
        raise ValueError("splits: {}: must be a positive integer.".format(
            splits))

    # Split the slice
    # Get the number of atoms, calculate how many per slice
    n_atoms = obj_slice.stop - obj_slice.start
    per_slice = int(math.ceil(n_atoms / float(splits)))

    # Build up the list of slices
    slices = []
    n = 0
    while n < n_atoms:
        slices.append(slice(n, min((n+per_slice, n_atoms))))
        n += per_slice

    return slices


def _create_derived_net(net, new_source, new_sinks):
    """Create a new net with the same properties as this one but with a
    replaced source and sinks.

    Override this to use the standard netlist partitioning methods with
    custom net types.
    """
    # Return a new net with the given source, sinks.  Copy over the weight
    # and get an of the keyspace if one is provided.
    return type(net)(
        new_source, new_sinks, net.weight,
        keyspace=None if net.keyspace is None else net.keyspace
    )


def partition_net(net, replacements,
                  create_derived_net=_create_derived_net):
    """Create new net(s) by replacing sinks and source(s) of an existing
    net.

    Parameters
    ----------
    net : :py:class:`~rig.netlist.Net`
        The net to partition.
    replacements : dict
        A mapping from objects to other objects or lists of objects.
    create_derived_net : callable
        A callable which accepts a :py:class:`~rig.netlist.Net`, a source
        object and a list of sink objects and which returns a copy of the
        original Net but with the source and sinks replaced.

    Returns
    -------
    list
        A list containing new net(s).

    If the source object requires replacing then a new net (or nets) will
    be produced with the replacement source(s).  If a sink object requires
    replacing then a single new net will be generated with the new sink(s)
    added as required.

        net = Net(obj_a, 1, [obj_b, obj_c])
        replacements = {obj_a: [obj_a1, obj_a2], obj_b: [obj_b1, obj_b2]}
        partition_net(net, replacements)
    """
    # Swap out sink objects
    new_sinks = list()

    for obj in net.sinks:
        if obj in replacements:
            # If the object is in the replacement map, then replace it.
            if isinstance(replacements[obj], list):
                # If the replacement is a list of new objects then add them
                new_sinks.extend(replacements[obj])
            else:
                # Otherwise just add the single new entry
                new_sinks.append(replacements[obj])
        else:
            # Otherwise retain it
            new_sinks.append(obj)

    # Swap out the source object if required
    if net.source in replacements:
        if isinstance(replacements[net.source], list):
            new_sources = replacements[net.source][:]
        else:
            new_sources = [replacements[net.source]]
    else:
        new_sources = [net.source]

    # Return the new net(s) by deriving from this net
    return [create_derived_net(net, source, new_sinks)
            for source in new_sources]
