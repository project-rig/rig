"""Fixed point conversion utilities.
"""
import numpy as np


def float_to_fix(signed, n_bits, n_frac):
    """Return a function to convert a floating point value to a fixed point
    value.

    Parameters
    ----------
    signed : bool
    n_bits : int
    n_frac : int
    """
    mask = int(2**n_bits - 1)
    min_v, max_v = validate_fp_params(signed, n_bits, n_frac)

    # Saturate values
    def bitsk(value):
        """Convert a floating point value to a fixed point value.

        Parameters
        ----------
        value : float
            The value to convert.
        """
        value = np.clip(value, min_v, max_v)

        if value < 0:
            fp_val = (1 << n_bits) + int(value * 2**n_frac)
        else:
            fp_val = int(value * 2**n_frac)

        assert 0 <= fp_val < 1 << (n_bits + 1)
        return fp_val & mask

    return bitsk


def fix_to_float(signed, n_bits, n_frac):
    """Return a function to convert a fixed point value to a floating point
    value.

    Parameters
    ----------
    signed : bool
    n_bits : int
    n_frac : int
    """
    validate_fp_params(signed, n_bits, n_frac)

    def kbits(value):
        """Convert a fixed point value to a float.

        Parameters
        ----------
        value : int
            The fix point value as an integer.
        """
        if signed and value & (1 << (n_bits - 1)):
            # If signed and negative
            return -(value & (2**(n_bits - 1) - 1)) / (2.0**n_frac)
        else:
            # Unsigned or signed and positive
            return float(value) / (2.0**n_frac)

    return kbits


class NumpyFloatToFixConverter(object):
    """A callable which converts Numpy arrays of floats to fixed point arrays.
    """
    dtypes = {
        (False, 8): np.uint8,
        (True, 8): np.int8,
        (False, 16): np.uint16,
        (True, 16): np.int16,
        (False, 32): np.uint32,
        (True, 32): np.int32,
        (False, 64): np.uint64,
        (True, 64): np.int64,
    }

    def __init__(self, signed, n_bits, n_frac):
        """Create a new converter from floats into ints.

        Parameters
        ----------
        signed : bool
            Indicates that the converted values are to be signed or otherwise.
        n_bits : int
            The number of bits each value will use overall (must be 8, 16, 32,
            or 64).
        n_frac : int
            The number of fractional bits.
        """
        self.min_value, self.max_value = validate_fp_params(
            signed, n_bits, n_frac)

        # Check the number of bits is sane
        if n_bits not in [8, 16, 32, 64]:
            raise ValueError(
                "n_bits: {}: Must be 8, 16, 32 or 64.".format(n_bits))

        # Store the settings
        self.bytes_per_element = n_bits / 8
        self.dtype = self.dtypes[(signed, n_bits)]
        self.n_frac = n_frac

    def __call__(self, values):
        """Convert the given NumPy array of values into fixed point format."""
        # Saturate the values
        vals = np.clip(values, self.min_value, self.max_value)

        # Scale and cast to appropriate int types
        vals *= 2.0 ** self.n_frac
        vals = np.round(vals)

        return self.dtype(vals)


def validate_fp_params(signed, n_bits, n_frac):
    # Check the number of bits is sane
    if n_bits < 1:
        raise ValueError("n_bits: {}: Must be greater than 1.".format(n_bits))

    # Check the number of bits is possible
    signed_bit = 1 if signed else 0
    if signed_bit + n_frac > n_bits or n_frac < 0:
        raise ValueError(
            "n_frac: {}: Must be less than {} (and positive).".format(
                n_frac, n_bits - signed_bit)
        )

    # Account for the sign bit
    n_int = n_bits if not signed else n_bits - 1

    # Return the min and max values
    min_v = 0 if not signed else -(1 << (n_int - n_frac))
    max_v = ((1 << n_int) - 1) / float(1 << n_frac)

    return min_v, max_v
