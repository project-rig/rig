'XYP' routing keys with BitField
================================

.. doctest::

    >>> from rig.bitfield import BitField
    
    >>> # Define a classic 'XYP' routing key format
    >>> b = BitField(32)
    >>> b.add_field("x", length=8, start_at=24)
    >>> b.add_field("y", length=8, start_at=16)
    >>> b.add_field("p", length=5, start_at=11)
    >>> b.add_field("neuron", length=11, start_at=0)
    
    >>> # Define some keys
    >>> my_favourite_core = b(x=1, y=2, p=3)
    >>> neurons = [my_favourite_core(neuron=n) for n in range(10)]
    >>> for neuron in neurons:
    ...     print(hex(neuron.get_value()))
    0x1021800
    0x1021801
    0x1021802
    0x1021803
    0x1021804
    0x1021805
    0x1021806
    0x1021807
    0x1021808
    0x1021809

Reference:

* :py:class:`rig.bitfield.BitField`

Tutorial:

* :py:ref:`bitfield-tutorial`


Hierarchical routing keys with BitField
=======================================

.. doctest::

    >>> from rig.bitfield import BitField
    
    >>> # Define two types of key, distinguished by bit 31
    >>> b = BitField(32)
    >>> b.add_field("type", length=1, start_at=31)
    >>> type_0 = b(type=0)
    >>> type_1 = b(type=1)
    
    >>> # Each type can have different and overlapping fields
    >>> type_0.add_field("magic", length=8, start_at=0)
    >>> type_1.add_field("science", length=8, start_at=4)
    
    >>> # Define some keys
    >>> print(hex(type_0(magic=0xAB).get_value()))
    0xab
    >>> print(hex(type_1(science=0xCD).get_value()))
    0x80000cd0
    
    >>> # Can't access fields from other parts of the hierarchy
    >>> type_0(science=123)  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
      ...
    rig.bitfield.UnavailableFieldError: Field 'science' is not available when 'type':1.

Reference:

* :py:class:`rig.bitfield.BitField`

Tutorial:

* :py:ref:`bitfield-tutorial`
