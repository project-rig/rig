"""Generic correctness tests applicable to all allocation algorithms."""

from rig.place_and_route.allocate.utils import slices_overlap, align


def test_slices_overlap():
    # A then B
    assert not slices_overlap(slice(0, 1), slice(2, 3))
    assert not slices_overlap(slice(0, 2), slice(2, 4))

    # B then A
    assert not slices_overlap(slice(2, 3), slice(0, 1))
    assert not slices_overlap(slice(2, 4), slice(0, 2))

    # Empty sets shouldn't ever collide
    assert not slices_overlap(slice(0, 0), slice(0, 0))
    assert not slices_overlap(slice(0, 0), slice(1, 1))
    assert not slices_overlap(slice(0, 0), slice(0, 1))
    assert not slices_overlap(slice(1, 1), slice(0, 0))
    assert not slices_overlap(slice(0, 1), slice(0, 0))

    # Non-empty sets overlapping exactly
    assert slices_overlap(slice(3, 8), slice(3, 8))

    # A overlaps bottom of B
    assert slices_overlap(slice(0, 2), slice(1, 2))
    assert slices_overlap(slice(0, 2), slice(1, 3))
    assert slices_overlap(slice(0, 2), slice(0, 3))
    assert slices_overlap(slice(0, 2), slice(0, 2))

    # B overlaps bottom of A
    assert slices_overlap(slice(1, 2), slice(0, 2))
    assert slices_overlap(slice(1, 3), slice(0, 2))
    assert slices_overlap(slice(0, 3), slice(0, 2))
    assert slices_overlap(slice(0, 2), slice(0, 2))


def test_align():
    # Exhaustively check a range of values
    for alignment in range(1, 8):
        assert align(0, alignment) == 0
        for target in [x*alignment for x in range(1, 8)]:
            for offset in range(alignment):
                assert align(target - offset, alignment) == target
