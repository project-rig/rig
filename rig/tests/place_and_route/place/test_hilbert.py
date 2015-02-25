import pytest

from rig.place_and_route.place.hilbert import hilbert


class TestHilbert(object):
    """Tests for Hilbert curve iterator."""

    def test_order(self):
        """Exhaustively test a few small cases to check order is correct."""
        assert list(hilbert(0)) == [(0, 0)]
        assert list(hilbert(1)) == [(0, 0), (0, 1), (1, 1), (1, 0)]
        assert list(hilbert(2)) == [
            (0, 0), (1, 0), (1, 1), (0, 1),
            (0, 2), (0, 3), (1, 3), (1, 2),
            (2, 2), (2, 3), (3, 3), (3, 2),
            (3, 1), (2, 1), (2, 0), (3, 0)]

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
    def test_completeness(self, level):
        """Test a handful of larger cases to ensure they cover every
        position.
        """
        extent = 2**level
        reference = set((x, y) for x in range(extent) for y in range(extent))
        for xy in hilbert(level):
            assert xy in reference
            reference.remove(xy)

        assert len(reference) == 0
