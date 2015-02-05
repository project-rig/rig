"""Utility functions for implementing allocation algorithms."""


def slices_overlap(slice_a, slice_b):
    """Test if the ranges covered by a pair of slices overlap."""
    assert slice_a.step is None
    assert slice_b.step is None

    return max(slice_a.start, slice_b.start) \
        < min(slice_a.stop, slice_b.stop)


def align(value, alignment):
    """Align `value` upward towards the nearest multiple of `alignment`."""
    return ((value + alignment - 1) // alignment) * alignment
