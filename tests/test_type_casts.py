import numpy as np
import pytest
from rig.type_casts import float_to_fix, fix_to_float, NumpyFloatToFixConverter
import struct


class TestFloatToFix(object):
    """Test converting from a float to a fixed point.
    """
    @pytest.mark.parametrize(
        "signed, n_bits, n_frac",
        [(True, 32, 32),  # Too many frac bits
         (False, 32, 33),
         (False, -1, 3),
         (False, 32, -1),  # Negative
         ])
    def test_invalid_parameters(self, signed, n_bits, n_frac):
        with pytest.raises(ValueError):
            float_to_fix(signed, n_bits, n_frac)

    @pytest.mark.parametrize(
        "value, n_bits, n_frac, output",
        [(0.50, 8, 4, 0x08),
         (0.50, 8, 5, 0x10),
         (0.50, 8, 6, 0x20),
         (0.50, 8, 7, 0x40),
         (0.50, 8, 8, 0x80),
         (0.25, 8, 4, 0x04),
         (0.75, 8, 4, 0x0c),
         (1.75, 8, 4, 0x1c),
         (-1.75, 8, 4, 0x00),  # Clipped
         ])
    def test_no_saturate_unsigned(self, value, n_bits, n_frac, output):
        assert float_to_fix(False, n_bits, n_frac)(value) == output

    @pytest.mark.parametrize(
        "value, n_bits, n_frac, output",
        [(0.50, 8, 4, 0x08),
         (0.50, 8, 5, 0x10),
         (0.50, 8, 6, 0x20),
         (0.50, 8, 7, 0x40),
         (0.25, 8, 4, 0x04),
         (0.75, 8, 4, 0x0c),
         (-.50, 8, 4, 0xf8),
         (-.50, 8, 5, 0xf0),
         (-.50, 8, 6, 0xe0),
         (-.50, 8, 7, 0xc0),
         (-.25, 8, 4, 0xfc),
         (-.75, 8, 4, 0xf4),
         (-.25, 8, 1, 0x00),
         (1.75, 8, 4, 0x1c),
         (-1.75, 8, 4, 0xe4),
         (-2.75, 8, 4, 0xd4),
         (-1.0, 8, 4, 0xf0),
         (-7.9375, 8, 4, 0x81),
         (-8, 8, 4, 0x80),
         (-16, 8, 4, 0x80),
         (-1.0, 8, 3, 0xf8),
         (-1.0, 8, 2, 0xfc),
         (-1.0, 8, 1, 0xfe),
         (-1.0, 16, 1, 0xfffe),
         (-1.0, 16, 2, 0xfffc),
         ])
    def test_no_saturate_signed(self, value, n_bits, n_frac, output):
        assert float_to_fix(True, n_bits, n_frac)(value) == output

    @pytest.mark.parametrize(
        "value, n_bits, n_frac, output",
        [(2**4, 8, 4, 0xff),  # Saturate
         (2**4 - 1 + sum(2**-n for n in range(1, 6)), 8, 4, 0xff),  # Saturate
         ])
    def test_saturate_unsigned(self, value, n_bits, n_frac, output):
        assert float_to_fix(False, n_bits, n_frac)(value) == output


class TestFixToFloat(object):
    @pytest.mark.parametrize(
        "signed, n_bits, n_frac",
        [(True, 32, 32),  # Too many frac bits
         (False, 32, 33),
         (False, -1, 3),
         (False, 32, -1),  # Negative
         ])
    def test_invalid_parameters(self, signed, n_bits, n_frac):
        with pytest.raises(ValueError):
            fix_to_float(signed, n_bits, n_frac)

    @pytest.mark.parametrize(
        "bits, signed, n_bits, n_frac, value",
        [(0xff, False, 8, 0, 255.0),
         (0x81, True, 8, 0, -127.0),
         (0xff, False, 8, 1, 127.5),
         (0xf8, True, 8, 4, -0.5)
         ])
    def test_fix_to_float(self, bits, signed, n_bits, n_frac, value):
        assert value == fix_to_float(signed, n_bits, n_frac)(bits)


class TestNumpyFloatToFixConverter(object):
    @pytest.mark.parametrize(
        "signed, n_bits, n_frac",
        [(True, 32, 32),  # Too many frac bits
         (False, 32, 33),
         (False, 32, -1),
         (False, -1, 1),
         (False, 31, 30),  # Weird number of bits
         ])
    def test_init_fails(self, signed, n_bits, n_frac):
        with pytest.raises(ValueError):
            NumpyFloatToFixConverter(signed, n_bits, n_frac)

    @pytest.mark.parametrize(
        "signed, n_bits, dtype, n_bytes",
        [(False, 8, np.uint8, 1),
         (True, 8, np.int8, 1),
         (False, 16, np.uint16, 2),
         (True, 16, np.int16, 2),
         (False, 32, np.uint32, 4),
         (True, 32, np.int32, 4),
         (False, 64, np.uint64, 8),
         (True, 64, np.int64, 8),
         ])
    def test_dtypes(self, signed, n_bits, dtype, n_bytes):
        """Check that the correcy dtype is returned."""
        fpf = NumpyFloatToFixConverter(signed, n_bits, 0)
        assert fpf.dtype == dtype
        assert fpf.bytes_per_element == n_bytes

    @pytest.mark.parametrize(
        "n_bits, n_frac, values, dtype",
        [(8, 4, [0.5, 0.25, 0.125, 0.0625], np.uint8),
         (8, 3, [0.5, 0.25, 0.125, 0.0625], np.uint8),
         (8, 2, [0.5, 0.25, 0.125, 0.0625], np.uint8),
         (8, 1, [0.5, 0.25, 0.125, 0.0625], np.uint8),
         (8, 0, [0.5, 0.25, 0.125, 0.0625], np.uint8),
         (8, 8, [0.5, 0.25, 0.125, 0.0625], np.uint8),
         (16, 12, [0.5, 0.25, 0.125, 0.0625], np.uint16),
         (32, 15, [0.5, 0.25, 0.125, 0.0625], np.uint32),
         ])
    def test_unsigned_no_saturate(self, n_bits, n_frac, values, dtype):
        # Create the formatter then call it on the array
        fpf = NumpyFloatToFixConverter(False, n_bits, n_frac)
        vals = fpf(np.array(values))

        # Check the values are correct
        ftf = float_to_fix(False, n_bits, n_frac)
        assert np.all(vals == np.array([ftf(v) for v in values]))
        assert vals.dtype == dtype

    @pytest.mark.parametrize(
        "n_bits, n_frac, values, dtype",
        [(8, 4, [0.5, 0.25, 0.125, 0.0625, -0.5], np.int8),
         (8, 3, [0.5, 0.25, 0.125, 0.0625, -0.25], np.int8),
         (8, 2, [0.5, 0.25, 0.125, 0.0625, -0.33], np.int8),
         (8, 1, [0.5, 0.25, 0.125, 0.0625, -0.25], np.int8),
         (8, 0, [0.5, 0.25, 0.125, 0.0625, -0.23], np.int8),
         (16, 12, [0.5, 0.25, 0.125, 0.0625, -0.45], np.int16),
         (32, 15, [0.5, 0.25, 0.125, 0.0625, -0.77], np.int32),
         ])
    def test_signed_no_saturate(self, n_bits, n_frac, values, dtype):
        # Create the formatter then call it on the array
        fpf = NumpyFloatToFixConverter(True, n_bits, n_frac)
        vals = fpf(np.array(values))

        c = {8: 'B', 16: 'H', 32: 'I'}[n_bits]

        # Check the values are correct
        ftf = float_to_fix(True, n_bits, n_frac)
        assert vals.dtype == dtype
        assert (  # pragma: no branch
            bytes(vals.data) ==
            struct.pack("{}{}".format(len(values), c),
                        *[ftf(v) for v in values])
        )

    @pytest.mark.parametrize("signed", [True, False])
    @pytest.mark.parametrize(
        "n_bits, n_frac",
        [(8, 0), (8, 4), (16, 5), (32, 27)])
    def test_saturate(self, signed, n_bits, n_frac):
        # Build the values
        values = [2.0**(n_bits - n_frac - (1 if signed else 0)),
                  2.0**(n_bits - n_frac - (1 if signed else 0)) - 1]

        # Format
        fpf = NumpyFloatToFixConverter(signed, n_bits, n_frac)
        vals = fpf(np.array(values))

        c = {8: 'B', 16: 'H', 32: 'I'}[n_bits]

        # Check the values are correct
        ftf = float_to_fix(signed, n_bits, n_frac)
        assert (  # pragma: no branch
            bytes(vals.data) ==
            struct.pack("{}{}".format(len(values), c),
                        *[ftf(v) for v in values])
        )
