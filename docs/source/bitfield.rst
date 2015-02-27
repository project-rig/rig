.. py:module::rig.bitfield
.. py:class::rig.bitfield.BitField

Defining bit fields with :py:class:`.BitField`
==============================================

In many applications there is a need to define bit fields, for example when
defining SpiNNaker routing keys. Rig provides the class
:py:class:`rig.bitfield.BitField` which allows the definition of hierarchical
bit fields. A tutorial introduction to this class is provided below and is
followed by the full API documentation.

Tutorial
--------

In this tutorial we will tackle the commonly faced challenge of defining the
SpiNNaker routing keys. In SpiNNaker, routing keys are 32-bit values which are
used to uniquely identify multicast streams of packets flowing from one core to
many others. We'll walk through a few simple example scenarios and demonstrate
the key features of :py:class:`.BitField`\ s.

Defining a basic bit field
^^^^^^^^^^^^^^^^^^^^^^^^^^

We'll start by defining a 32-bit bit field:

.. doctest::

    >>> from rig.bitfield import BitField
    >>> b = BitField(32)
    >>> b
    <32-bit BitField >

Initially no fields are defined and so we must define some. Lets define the
following fields:

`chip`
    Bits 31-16: The unique chip ID number of the chip which produced the packet.
`core`
    Bits 12-8: The core ID number of the core which produced the packet.
`type`
    Bits 7-0: Some application specific message-type indicator.

These fields can be defined like so:

.. doctest::

    >>> b.add_field("chip", length=16, start_at=16)
    >>> b.add_field("core", length=5, start_at=8)
    >>> b.add_field("type", length=8, start_at=0)
    >>> b
    <32-bit BitField 'chip':?, 'core':?, 'type':?>

We can now specify the value of these fields to define a specific routing key:

.. doctest::

    >>> TYPE_START = 0x01
    >>> TYPE_STOP = 0x02
    >>> # ...
    
    >>> start_master = b(chip=1024, core=1, type=TYPE_START)
    >>> start_master
    <32-bit BitField 'chip':1024, 'core':1, 'type':1>

Notice that a new :py:class:`.BitField` is produced but this one has its fields
allocated specific values.

.. note::
    The newly created :py:class:`.BitField` is linked to the original
    :py:class:`.BitField`. Amongst other things this means that if new fields
    are added to the original, they will also appear in this bit field. The
    utility of this will become more apparent later.

Since all the fields (and their lengths and positions) in `start_master` have
been defined, we can use the :py:meth:`.get_value` and :py:meth:`.get_mask`
methods to get the actual binary value of the bit field and also a mask which
selects only those bits used by a field in the bit field:

.. doctest::

    >>> # Get the binary value of the bit field with these field values
    >>> hex(start_master.get_value())
    '0x4000101'
    
    >>> # Get a mask which includes only fields in the bit field. (Note that this
    >>> # bit field has a few bits in the middle which aren't part of any fields).
    >>> hex(start_master.get_mask())
    '0xffff1fff'

We don't have to define all the fields at once, however. We can also specify
just some fields at a time like so:

.. doctest::

    >>> master_core = b(chip=1024, core=1)
    >>> master_core
    <32-bit BitField 'chip':1024, 'core':1, 'type':?>

This is useful because we can pass the `master_core` :py:class:`.BitField`
around where fields are completed later:

.. doctest::

    >>> start_master = master_core(type=TYPE_START)
    >>> stop_master = master_core(type=TYPE_STOP)
    
    >>> start_master
    <32-bit BitField 'chip':1024, 'core':1, 'type':1>
    >>> hex(start_master.get_value())
    '0x4000101'
    
    >>> stop_master
    <32-bit BitField 'chip':1024, 'core':1, 'type':2>
    >>> hex(stop_master.get_value())
    '0x4000102'


Automatically allocating fields to bits
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In many cases, we don't really care exactly how our bit field is formatted. All
we care is that the fields do not overlap and that they are large enough to
represent the largest value assigned to that field. As a result, we can omit
one or both of the `length` and `start_at` options to let :py:class:`.BitField`
automatically allocate and position fields:

.. doctest::

    >>> # Starting a new example 32-bit bit field
    >>> b = BitField(32)
    >>> b.add_field("chip")
    >>> b.add_field("core")
    >>> b.add_field("type")
    >>> b
    <32-bit BitField 'chip':?, 'core':?, 'type':?>

.. note::
    It is perfectly valid to mix fields both with and without allocated lengths
    and positions. :py:class:`.BitField` will automatically verify that the
    fields created do not overlap.

Just as before, we can assign new values to each field:

.. doctest::

    >>> TYPE_START = 0x01
    >>> TYPE_STOP = 0x02
    >>> # ...

    >>> start_master = b(chip=1024, core=1, type=TYPE_START)
    >>> start_master
    <32-bit BitField 'chip':1024, 'core':1, 'type':1>
    
    >>> master_core = b(chip=1024, core=1)
    >>> master_core
    <32-bit BitField 'chip':1024, 'core':1, 'type':?>
    >>> start_master = master_core(type=TYPE_START)
    >>> start_master
    <32-bit BitField 'chip':1024, 'core':1, 'type':1>
    >>> stop_master = master_core(type=TYPE_STOP)
    >>> stop_master
    <32-bit BitField 'chip':1024, 'core':1, 'type':2>

At the moment, the three fields do not have a designated length or position in
the bit field. Before we can use :py:meth:`.get_value` and :py:meth:`.get_mask`
we must assign all fields a length and position using :py:meth:`.assign_fields`:

.. doctest::

    >>> # Oops: Fields haven't been assigned lengths and positions yet!
    >>> hex(start_master.get_value())
    Traceback (most recent call last):
      File "<stdin>", line 2, in ?
    ValueError: Field 'chip' does not have a fixed size/position.

    >>> b.assign_fields()
    >>> hex(start_master.get_value())
    '0x1c00'
    >>> hex(stop_master.get_value())
    '0x2c00'

We can use :py:meth:`.get_mask` to see what bits in the bit field were
allocated to each field like so:

.. doctest::

    >>> # What is the total set of bits used
    >>> hex(b.get_mask())
    '0x3fff'
    
    >>> # Which bits are used for each field
    >>> hex(b.get_mask(field="chip"))
    '0x7ff'
    >>> hex(b.get_mask(field="core"))
    '0x800'
    >>> hex(b.get_mask(field="type"))
    '0x3000'

You'll see that the three fields have been assigned to three non-overlapping
sets of bits in the bit field. We can also see that the `chip` field has been
allocated 10 bits which is large enough to fit the largest value we assigned to
that field, `1024`. Likewise, the `core` and `type` fields have been allocated
one and two bits respectively to accommodate the values we provided.

.. warning::
    When using dynamically lengthed/positioned fields, it is important that all
    bit field values are assigned before calling :py:meth:`.assign_fields`. If
    this is not the case, the fields may not be allocated adequate lengths to
    fit the values required. The implication of this is that applications
    should generally operate in two phases:
    
    1. Assignment of field values (prior to :py:meth:`.assign_fields`)
    2. Generation of binary values and masks (after :py:meth:`.assign_fields`)

Defining hierarchical bit fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Fields can also exist in a hierarchical structure. For example, packets to/from
external devices may use a different set of fields to those used
internally between cores. In our example, we'll define that bit 31 of the key
is `0` for internal packets and `1` for external packets. We can define this as
a field as usual:

.. doctest::

    >>> # Starting another new example...
    >>> b = BitField(32)
    >>> b.add_field("external", length=1, start_at=31)
    >>> b
    <32-bit BitField 'external':?>

In this example, internal packets will have fields `chip`, `core` and `type` as
before while external packets will have the fields `device_id` and `command`.
These can be defined like so:

.. doctest::

    >>> # Internal fields
    >>> b_internal = b(external=0)
    >>> b_internal.add_field("chip")
    >>> b_internal.add_field("core")
    >>> b_internal.add_field("type")

    >>> # External fields
    >>> b_external = b(external=1)
    >>> b_external.add_field("device_id")
    >>> b_external.add_field("command")

Notice that to add fields which appear only when `external` is `0` or `1` we
add them to the :py:class:`.BitField` with the `external` field set to the
appropriate value.

.. note::
    As mentioned earlier, all :py:class:`.BitField`\ s associated with the
    same bit field are linked and so adding fields to these derived
    :py:class:`.BitField` objects (i.e. `b_internal` and `b_external`) effects
    the whole bit field.

Now, whenever the `external` field is '0' we have fields `external`, `chip`,
`core` and `type`. Whenever the `external` field is '1' we have fields
`external`, `device_id` and `command`:

.. doctest::

    >>> b
    <32-bit BitField 'external':?>
    >>> b(external=0)
    <32-bit BitField 'external':0, 'chip':?, 'core':?, 'type':?>
    >>> b(external=1)
    <32-bit BitField 'external':1, 'device_id':?, 'command':?>

Finally, defining values works exactly as we've seen before:

.. doctest::

    >>> # Setting all fields at once
    >>> example_internal = b(external=0, chip=0, core=1, type=TYPE_START)
    >>> example_internal
    <32-bit BitField 'external':0, 'chip':0, 'core':1, 'type':1>
    >>> example_external = b(external=1, device_id=0xBEEF, command=0x0)
    >>> example_external
    <32-bit BitField 'external':1, 'device_id':48879, 'command':0>
    
    >>> # Setting fields incrementally
    >>> master_core = b(external=0, chip=1, core=1)
    >>> master_core
    <32-bit BitField 'external':0, 'chip':1, 'core':1, 'type':?>
    >>> start_master = master_core(type=TYPE_START)
    >>> start_master
    <32-bit BitField 'external':0, 'chip':1, 'core':1, 'type':1>
    
    >>> # Assign fields to bits to see where things ended up
    >>> b.assign_fields()
    >>> hex(b.get_mask())
    '0x80000000'
    >>> hex(b(external=0).get_mask())
    '0x80000007'
    >>> hex(b(external=1).get_mask())
    '0x8001ffff'

Because the `device_id` and `command` fields and the `chip`, `core` and `type`
fields are never present in the same key, they may be allocated overlapping
sets of bits. In this example, the lower bits of the bit field are used by both
groups of fields depending on the value of `external`.

Selecting subsets of fields using tags
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In many applications using bit fields, some fields are not relevant in every
circumstance. For example, given our SpiNNaker routing key example, only the
`chip` and `core` fields may be relevant to routing since the `type` field is
only relevant to the receiving cores. As a result when building routing tables
it is useful to only consider `chip` and `core` while in our application code
we may only consider the `type`.

To facilitate this, fields can be labelled with tags like so:

.. doctest::

    >>> # Starting yet another new example...
    >>> b = BitField(32)
    >>> b.add_field("chip", tags="routing")
    >>> b.add_field("core", tags="routing")
    >>> b.add_field("type", tags="application")
    >>> b
    <32-bit BitField 'chip':?, 'core':?, 'type':?>

We can now use the `tag` arguments to :py:meth:`.get_value` and
:py:meth:`.get_mask` to generate binary values and masks for just the fields
with that tag:

.. doctest::

    >>> # Assign values like usual...
    >>> master_core = b(chip=1024, core=1)
    >>> stop_master = master_core(type=TYPE_STOP)
    >>> b.assign_fields()

    >>> hex(master_core.get_value(tag="routing"))
    '0xc00'
    >>> hex(master_core.get_mask(tag="routing"))
    '0xfff'
    >>> hex(stop_master.get_value(tag="application"))
    '0x2000'
    >>> hex(stop_master.get_mask(tag="application"))
    '0x3000'

.. note::
    When used with a tag, :py:meth:`.get_value` only requires that the fields
    with the specified tag have a value. Notice how it could be successfully
    called on `master_core` with the tag `routing` which doesn't have the
    `type` field set.

When using hierarchical bit fields, assigning a tag to a field also assigns
that tag to all fields above it in the hierarchy. For example in:

.. doctest::

    >>> # Starting yet another new example...
    >>> b = BitField(32)
    >>> b.add_field("external")
    
    >>> b_internal = b(external=0)
    >>> b_internal.add_field("chip", tags="routing")
    >>> b_internal.add_field("core", tags="routing")
    >>> b_internal.add_field("type", tags="application")
    
    >>> b_external = b(external=1)
    >>> b_external.add_field("device_id", tags="routing")
    >>> b_external.add_field("command")

The following tags are assigned:

+-----------+----------------------+
| Field     |  Tags                |
+===========+======================+
| external  | routing, application |
+-----------+----------------------+
| chip      | routing              |
+-----------+----------------------+
| core      | routing              |
+-----------+----------------------+
| type      | application          |
+-----------+----------------------+
| device_id | routing              |
+-----------+----------------------+
| command   |                      |
+-----------+----------------------+

This behaviour is important since fields with a given tag only exist when those
further up the hierarchy have specific values. In other words: when checking that
a given set of tagged fields have a certain value, we must equally check that
those fields are present.

Allowing 3rd party expansion of bit fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In certain applications, it can be useful to allow two completely separate
code-bases share the same bit field. For example, a SpiNNaker application may
wish to support a range of plugins and as a result the application and its
plugins must be careful not to produce routing keys that interfere. Using the
:py:class:`.BitField` class, it is possible to support this safely and simply
like so:

.. doctest::

    >>> # One final example...
    >>> b = BitField(32)
    >>> b.add_field("user")
    >>> app_bitfield = b(user=0)
    >>> plugin_1_bitfield = b(user=1)
    >>> plugin_2_bitfield = b(user=2)
    >>> plugin_3_bitfield = b(user=3)
    >>> # ...

Each part of the application is then issued with its own :py:class:`.BitField`
instance (e.g. `app_bitfield`, `plugin_1_bitfield` etc.) to which new fields
may be assigned independently. These separate cases will never suffer any
collisions since each user's bit fields are distinguished by the `user` field.

.. note::
    The only care that need be taken is that field names must be unique within
    the bit field. As a result, users may name-space their fields by adopting a
    simple prefix.


:py:class:`.BitField` API
-------------------------------------

.. autoclass:: rig.bitfield.BitField
    :members:
    :special-members:

