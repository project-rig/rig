import mock
import pytest
import tempfile
from ..region import PrependedValue, PrependNumAtoms, Region


class TestRegion(object):
    @pytest.mark.parametrize("prepends", [
        [PrependedValue(1)],
        [PrependedValue(2)],
        [PrependedValue(4)],
        [PrependedValue(1), PrependedValue(4)],
        [PrependedValue(1), PrependedValue(2), PrependedValue(4)],
    ])
    def test_sizeof(self, prepends):
        """Check getting the base size of the region (all the prepends)."""
        r = Region(prepends=prepends)
        assert r.sizeof(slice(None)) == sum(p.n_bytes for p in prepends)

    def test_write_subregion_to_file(self):
        # Create two region prependers, these should return different
        # bytestrings when they are called.
        pp1 = mock.Mock(spec=PrependedValue)
        pp1.return_value = b'\x00\x01'
        pp2 = mock.Mock(spec=PrependedValue)
        pp2.return_value = b'\xfe\xca\xef\xbe'

        # Create a region with these prependers
        r = Region(prepends=[pp1, pp2])

        # Write a subregion to file, ensure that the written values are as
        # expected and that the correct calls were made to the prependers.
        f = tempfile.TemporaryFile()
        r.write_subregion_to_file(slice(0, 9), f)

        # Assert the contents of the file are correct
        f.seek(0)
        assert f.read(6) == pp1.return_value + pp2.return_value

        # Now assert that the correct calls were made
        for pp in r.prepends:
            pp.assert_called_once_with(slice(0, 9), r)


class TestPrependedValue(object):
    """Test the basic functionality of the prepended value class."""

    @pytest.mark.parametrize("n_bytes", [3, 5, 6, 7, 8, 9, 1000])
    def test_init_fails(self, n_bytes):
        """Check that values with invalid numbers of bytes cause failures."""
        with pytest.raises(ValueError):
            PrependedValue(n_bytes)

    @pytest.mark.parametrize("n_bytes,signed,val,bytestring", [
        (1, False, 1, b'\x01'),
        (1, True, 1, b'\x01'),
        (1, True, -1, b'\xff'),
        (2, False, 0xcafe, b'\xfe\xca'),
        (2, True, -2, b'\xfe\xff'),
        (4, False, 0xa5b7cafe, b'\xfe\xca\xb7\xa5'),
        (4, True, -2, b'\xfe\xff\xff\xff'),
    ])
    def test_format_value(self, n_bytes, signed, val, bytestring):
        # Create a new PrependedValue
        pv = PrependedValue(n_bytes, signed)

        # Check that the value is formatted correctly
        assert pv._format_value(val) == bytestring

    @pytest.mark.parametrize("vertex_slice", [
        slice(None),  # No start or stop
        slice(1),  # No start
        slice(3, 1),  # Start bigger than stop
    ])
    def test_prepend_call_value_errors(self, vertex_slice):
        """Tests that invalid slices result in ValueErrors."""
        pv = PrependedValue(1)

        with pytest.raises(ValueError):
            pv(vertex_slice, None)


@pytest.mark.parametrize("n_bytes,vertex_slice,bytestring", [
    (1, slice(0, 0), b'\x00'),
    (1, slice(0, 1), b'\x01'),
    (1, slice(0, 9), b'\x09'),
    (2, slice(2, 9), b'\x07\x00'),
    (4, slice(1, 9), b'\x08\x00\x00\x00'),
])
def test_prepend_n_atoms(n_bytes, vertex_slice, bytestring):
    # Create the prepender
    pv = PrependNumAtoms(n_bytes)

    # Check that the correct value is prepended
    assert pv(vertex_slice, None) == bytestring
