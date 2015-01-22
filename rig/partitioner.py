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
