Fixed point number conversion
=============================

.. doctest::
    
    >>> from rig.type_casts import float_to_fp, fp_to_float
    
    >>> # Create a function to convert a float to a signed fractional
    >>> # representation with 8 bits overall and 4 fractional bits (S3.4)
    >>> s34 = float_to_fp(signed=True, n_bits=8, n_frac=4)
    >>> hex(int(s34(0.5)))
    '0x8'
    >>> hex(int(s34(-7.5)))
    '-0x78'
    
    >>> # ...and make a function to convert back again!
    >>> f4 = fp_to_float(n_frac=4)
    >>> f4(0x08)
    0.5
    >>> f4(-0x78)
    -7.5

Reference:

* :py:func:`rig.type_casts.float_to_fp`
* :py:func:`rig.type_casts.fp_to_float`


Fixed point number conversion (for Numpy)
=========================================

.. doctest::
    
    >>> import numpy as np
    >>> from rig.type_casts import \
    ...     NumpyFloatToFixConverter, NumpyFixToFloatConverter
    
    >>> # Create a function to convert a float to a signed fractional
    >>> # representation with 8 bits overall and 4 fractional bits (S3.4)
    >>> s34 = NumpyFloatToFixConverter(signed=True, n_bits=8, n_frac=4)
    >>> vals = np.array([0.0, 0.25, 0.5, -0.5, -0.25])
    >>> s34(vals)
    array([ 0,  4,  8, -8, -4], dtype=int8)
    
    >>> # ...and make a function to convert back again!
    >>> f4 = NumpyFixToFloatConverter(4)
    >>> vals = np.array([ 0,  4,  8, -8, -4], dtype=np.int8)
    >>> f4(vals)
    array([ 0.  ,  0.25,  0.5 , -0.5 , -0.25])

Reference:

* :py:class:`rig.type_casts.NumpyFloatToFixConverter`
* :py:class:`rig.type_casts.NumpyFixToFloatConverter`
