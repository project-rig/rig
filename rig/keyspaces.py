"""A system for defining and representing routing keys.

See the :py:class:`~.spinnaker.keyspaces.Keyspace` class.
"""

from collections import OrderedDict

from math import log


class Keyspace(object):
    """Defines the format & value of routing keys for SpiNNaker.

    Notes
    -----
    This model presumes that routing keys are made up of a number of (unsigned,
    integral) fields. For example, there might be a field which specifies which
    chip a message is destined for, another which specifies the core and
    another which specifies the type of message::

        # Create a new 32-bit Keyspace
        ks = Keyspace(32)

        ks.add_field("chip")
        ks.add_field("core")
        ks.add_field("type")

    Given a keyspace with some fields defined, we can define the value of these
    fields to define a specific key::

        # Returns a new `Keyspace` object with the specified fields set
        # accordingly.
        start_master = ks(chip=0, core=1, type=0x01)

    We can also specify just some keys at a time. This means that the fields
    can be specified at different points in execution where it makes most
    sense. As an example::

        master_core = ks(chip=0, core=1)

        # chip = 0, core = 1, type = 0x01 (same as previous example)
        start_master = master_core(type=0x01)

        # chip = 0, core = 1, type = 0x02
        stop_master = master_core(type=0x02)

    Fields can also exist in a hierarchical structure. For example, we may have
    a field which defines that a key is destined for an external device which
    expects a different set of fields to those for internal use::

        # Starting a new example...
        ks2 = Keyspace(32)

        ks2.add_field("external")

        ks2_internal = ks2(external=0)
        ks2_internal.add_field("chip")
        ks2_internal.add_field("core")
        ks2_internal.add_field("type")

        ks2_external = ks2(external=1)
        ks2_internal.add_field("device_id")
        ks2_internal.add_field("command")

        # Keys can be derived from the top-level object
        example_internal = ks(external=0, chip=0, core=1, type=0x01)
        example_external = ks(external=1, device_id=0xBEEF, command=0x0)

    Now, whenever the `external` field is '0' we have fields `external`,
    `chip`, `core` and `type`. Whenever the `external` field is '1' we have
    fields `external`, `device_id` and `command`. In this example, the
    `device_id` and `command` fields are free to overlap with the `chip`,
    `core` and `type` fields since they are never present in the same key.

    APIs making use of the `Keyspace` module can use this mechanism to create
    'holes' in their keyspace within which API users can add their fields which
    are guaranteed not to collide with the API's key space. For example, we
    could allow developers to set up their own custom fields for their specific
    devices by exposing the following `Keyspace`::

        ks2(external = 1)

    Note only one `Keyspace` object should ever be directly constructed in an
    application from which all new keyspaces are produced ensuring that all
    fields are defined in a non-conflicting manner.

    Certain fields may have fixed lengths and positions within a routing key,
    for example, those required by a hardware peripheral. Conversely, some
    fields' lengths and positions are unimportant and are only required to be
    long enough to represent the maximum value held by a key. Lets re-write the
    above example but this time lets specify the length and position of the
    fields used by external peripherals while leaving internal fields' lengths
    and positions unspecified. These fields will be assigned a free space
    (working from the least-significant bit upwards) in the keyspace large
    enough for the largest value ever assigned to the field when we call
    `assign_fields()`.::

        ks3 = Keyspace(32)

        # Top-most bit
        ks3.add_field("external", length = 1, start_at = 31)

        # Length and position to be determined automatically
        ks3_internal = ks3(external = 0)
        ks3_internal.add_field("chip")
        ks3_internal.add_field("core")
        ks3_internal.add_field("type")

        # Manually specified field sizes/positions
        ks3_external = ks3(external = 1)
        ks3_internal.add_field("device_id", length=16, start_at=0)
        ks3_internal.add_field("command", length=4, start_at=24)

        start_master = ks3(external=0, chip=0, core=1, type=0x01)
        # ... assign all other keys ...

        # Set field sizes/positions accordingly
        ks3.assign_fields()

    In order to turn a `Keyspace` whose fields have been given values into an
    actual routing key we can use::

        print(hex(start_master.get_key()))

    We can also generate a mask which selects only those bits used by fields in
    the key::

        print(hex(start_master.get_mask()))

    Generating a key with `get_key()` requires that all fields involved have
    fixed lengths and positions. Note that `assign_fields()` sets field sizes
    according to the largest value observed being assigned to a field prior to
    that call. As a result, users should be careful to create keyspaces with
    all required field values prior to calling `assign_fields()` since fields
    cannot later be enlarged.

    With keys broken down into fields, routing can also be simplified by only
    routing based on only a subset of fields. Continuing our example we need
    only route based on the `external`, `device_id`, `chip` and `core` fields.
    In fact, we can route entirely based on `external`, `device_id` and `chip`
    when we're not on the target chip. If we re-write our keyspace definition
    one final time we can apply tags to these subsets of fields to enable us to
    easily generate keys/masks based only on these fields. When a tag is
    applied, it is added to all currently set fields too. This means we can
    easily identify the fields used for routing by just assigning a tag to the
    fields that, semantically, are actually used for routing.::

        ks4 = Keyspace(32)

        ks4.add_field("external", length=1, start_at=31)

        ks4_internal = ks4(external=0)
        ks4_internal.add_field("chip", tags="routing local_routing")
        ks4_internal.add_field("core", tags="local_routing")
        ks4_internal.add_field("type")

        ks4_external = ks4(external = 1)
        ks4_internal.add_field("device_id", length=16, start_at=0,
            tags = "routing local_routing")
        ks4_internal.add_field("command", length=4, start_at=24)

        start_master = ks4(external=0, chip=0, core=1, type=0x01)
        device = ks4(external = 1, device_id = 12)

        ks4.assign_fields()

        # Keys/masks for the target chip
        print(hex(start_master.get_key(tag="local_routing")))
        print(hex(start_master.get_mask(tag="local_routing")))

        # Keys/masks for other chips
        print(hex(start_master.get_key(tag="routing")))
        print(hex(start_master.get_mask(tag="routing")))

        # Keys/masks for a device (note that we don't need to define the
        # command field since it does not have the routing tag.
        print(hex(device.get_key(tag="routing")))
        print(hex(device.get_mask(tag="routing")))

        # Equivalently:
        print(hex(device.get_key(tag="local_routing")))
        print(hex(device.get_mask(tag="local_routing")))
    """

    def __init__(self, length=32, fields=None, field_values=None):
        """Create a new Keyspace.

        Parameters
        ----------
        length : int
            The total number of bits in routing keys.
        fields : dict
            For internal use only. The shared, global field dictionary.
        field_values : dict
            For internal use only. Mapping of field-identifier to value.
        """
        self.length = length

        # An OrderedDict if field definitions (globally shared by all
        # derivatives of the same keyspace) which maps human-friendly
        # field-identifiers (e.g.  strings) to corresponding Keyspace.Field
        # instances. An OrderedDict preserves insertion ordering which is used
        # to automatic field positioning more predictable and also ensures the
        # fields are stored under the partial ordering of their hierarchy (a
        # property used by this code).
        self.fields = fields if fields is not None else OrderedDict()

        if field_values is not None:
            self.field_values = field_values
        else:
            self.field_values = dict()

    def add_field(self, identifier, length=None, start_at=None, tags=None):
        """Add a new field to the Keyspace.

        If any existing fields' values are set, the newly created field will
        become a child of those fields. This means that this field will exist
        only when the parent fields' values are set as they are currently.

        Parameters
        ----------
        identifier : str
            A identifier for the field. Must be a valid python identifier.
            Field names must be unique and users are encouraged to sensibly
            name-space fields in the `prefix_` style to avoid collisions.
        length : int or None
            The number of bits in the field. If *None* the field will be
            automatically assigned a length long enough for the largest value
            assigned.
        start_at : int or None
            0-based index of least significant bit of the field within the
            keyspace. If *None* the field will be automatically located in free
            space in the keyspace.
        tags : string or collection of strings or None
            A (possibly empty) set of tags used to classify the field.  Tags
            should be valid Python identifiers. If a string, the string must be
            a single tag or a space-separated list of tags. If *None*, an empty
            set of tags is assumed. These tags are applied recursively to all
            fields of which this field is a child.

        Raises
        ------
        :py:class:`ValueError`
            If any the field overlaps with another one or does not fit within
            the Keyspace. Note that fields with unspecified lengths and
            positions do not undergo such checks until their length and
            position become known.
        """
        # Check for duplicate names
        if identifier in self.fields:
            raise ValueError(
                "Field with identifier '{}' already exists.".format(
                    identifier))

        # Check for zero-length fields
        if length is not None and length <= 0:
            raise ValueError("Fields must be at least one bit in length.")

        # Check for fields which don't fit in the keyspace
        if (start_at is not None
            and (0 <= start_at >= self.length
                 or start_at + (length or 1) > self.length)):
            raise ValueError(
                "Field doesn't fit within {}-bit keyspace.".format(
                    self.length))

        # Check for fields which occupy the same bits
        if start_at is not None:
            end_at = start_at + (length or 1)
            for other_identifier, other_field in self._potential_fields():
                if other_field.start_at is not None:
                    other_start_at = other_field.start_at
                    other_end_at = other_start_at + (other_field.length or 1)
                    if end_at > other_start_at and other_end_at > start_at:
                            raise ValueError(
                                "Field '{}' (range {}-{}) "
                                "overlaps field '{}' (range {}-{})".format(
                                    identifier,
                                    start_at, end_at,
                                    other_identifier,
                                    other_start_at, other_end_at))

        # Normalise tags type
        if type(tags) is str:
            tags = set(tags.split())
        elif tags is None:
            tags = set()
        else:
            tags = set(tags)

        # Add tags to all parents of this field
        parent_identifiers = list(self.field_values.keys())
        while parent_identifiers:
            parent_identifier = parent_identifiers.pop(0)
            parent = self.fields[parent_identifier]
            parent.tags.update(tags)
            parent_identifiers.extend(parent.conditions.keys())

        # Add the field
        self.fields[identifier] = Keyspace.Field(
            length, start_at, tags, dict(self.field_values))

    def __call__(self, **field_values):
        """Return a new Keyspace instance with fields assigned values as
        specified in the keyword arguments.

        Returns
        -------
        :py:class:`~.spinnaker.keyspaces.Keyspace`
            A `Keyspace` derived from this one but with the specified fields
            assigned a value.

        Raises
        ------
        :py:class:`ValueError`
            If any field has already been assigned a value or the value is too
            large for the field.
        :py:class:`AttributeError`
            If a field is specified which is not present.
        """
        # Ensure fields exist
        for identifier in field_values.keys():
            if identifier not in self.fields:
                raise ValueError("Field '{}' not defined.".format(identifier))

        # Make sure no values are changed
        for identifier, value in self.field_values.items():
            if identifier in field_values:
                raise ValueError(
                    "Field '{}' already has value.".format(identifier))

        field_values.update(self.field_values)

        # Ensure no fields are specified which are not enabled
        for identifier in field_values:
            self._assert_field_available(identifier, field_values)

        # Ensure values are within range
        for identifier, value in field_values.items():
            field_length = self.fields[identifier].length
            if value < 0:
                raise ValueError("Fields must be positive.")
            elif field_length is not None and value >= (1 << field_length):
                raise ValueError(
                    "Value {} too large for {}-bit field '{}'.".format(
                        value, field_length, identifier))

        # Update maximum observed values
        for identifier, value in field_values.items():
            self.fields[identifier].max_value = max(
                self.fields[identifier].max_value, value)

        return Keyspace(self.length, self.fields, field_values)

    def __getattr__(self, identifier):
        """Get the value of a field.

        Returns
        -------
        int or None
            The value of the field (or None if the field has not been given a
            value).

        Raises
        ------
        :py:class:`AttributeError`
            If the field requested does not exist or is not available given
            current field values.
        """
        self._assert_field_available(identifier)
        return self.field_values.get(identifier, None)

    def get_key(self, tag=None, field=None):
        """Generate a key whose fields are set appropriately and with all other
        bits set to zero.

        Parameters
        ----------
        tag : str
            Optionally specifies that the key should only include fields with
            the specified tag.
        field : str
            Optionally specifies that the key should only include the specified
            field.

        Raises
        ------
        :py:class:`ValueError`
            If a field whose length or position has not been defined. (i.e.
            `assign_fields()` has not been called when a field's size/position
            has not been fixed.
        """
        assert not (tag is not None and field is not None), \
            "Cannot filter by tag and field simultaneously."

        # Build a filtered list of fields to be used in the key
        if field is not None:
            self._assert_field_available(field)
            selected_field_idents = [field]
        elif tag is not None:
            self._assert_tag_exists(tag)
            selected_field_idents = [i for (i, f) in self._enabled_fields()
                                     if tag in f.tags]
        else:
            selected_field_idents = [i for (i, f) in self._enabled_fields()]

        # Check all selected fields are defined
        missing_fields_idents = \
            set(selected_field_idents) - set(self.field_values.keys())
        if missing_fields_idents:
            raise ValueError(
                "Cannot generate key with undefined fields {}.".format(
                    ", ".join(missing_fields_idents)))

        # Build the key
        key = 0
        for identifier in selected_field_idents:
            field = self.fields[identifier]
            if field.length is None or field.start_at is None:
                raise ValueError(
                    "Field '{}' does not have a fixed size/position.".format(
                        identifier))
            key |= (self.field_values[identifier] <<
                    field.start_at)

        return key

    def get_mask(self, tag=None, field=None):
        """Get the mask for all fields which exist in the current keyspace.

        Parameters
        ----------
        tag : str
            Optionally specifies that the mask should only include fields with
            the specified tag.
        field : str
            Optionally specifies that the mask should only include the
            specified field.

        Raises
        ------
        :py:class:`ValueError`
            If a field whose length or position has not been defined. (i.e.
            `assign_fields()` has not been called when a field's size/position
            has not been fixed.
        """
        assert not (tag is not None and field is not None)

        # Build a filtered list of fields to be used in the key
        if field is not None:
            self._assert_field_available(field)
            selected_field_idents = [field]
        elif tag is not None:
            self._assert_tag_exists(tag)
            selected_field_idents = [i for (i, f) in self._enabled_fields()
                                     if tag in f.tags]
        else:
            selected_field_idents = [i for (i, f) in self._enabled_fields()]

        # Build the mask (and throw an exception if we encounter a field
        # without a fixed size/length.
        mask = 0
        for identifier in selected_field_idents:
            field = self.fields[identifier]
            if field.length is None or field.start_at is None:
                raise ValueError(
                    "Field '{}' does not have a fixed size/position.".format(
                        identifier))
            mask |= ((1 << field.length) - 1) << field.start_at

        return mask

    def assign_fields(self):
        """Assign a position & length to any fields which do not have one.

        Users should typically call this method after all field values have
        been assigned to keyspaces otherwise fields may be fixed at an
        inadequate size.
        """
        # We must fix fields at every level of the heirarchy sepeartely
        # (otherwise fields of children won't be allowed to overlap). Here we
        # do a breadth-first iteration over the heirarchy, fixing the fields at
        # each level.
        unsearched_heirarchy = [Keyspace(self.length, self.fields)]
        while unsearched_heirarchy:
            ks = unsearched_heirarchy.pop(0)
            ks._assign_enabled_fields()
            # Look for potential children in the herarchy
            for identifier, field in ks._potential_fields():
                enabled_field_idents = set(i for (i, f) in
                                           ks._enabled_fields())
                set_fields = {}
                for cond_ident, cond_value in field.conditions.items():
                    # Fail if not a child
                    if cond_ident not in enabled_field_idents:
                        self.set_fields = {}
                        break
                    # Accumulate fields which must be set
                    if getattr(ks, cond_ident) is None:
                        set_fields[cond_ident] = cond_value
                if set_fields:
                    unsearched_heirarchy.append(ks(**set_fields))

    def __eq__(self, other):
        """Test that this keyspace is equivalent to another.

        In order to be equal, the other keyspace must be a descendent of the
        same original Keyspace (and thus will *always* have exactly the same
        set of fields). It must also have the same field values defined.
        """
        return (self.length == other.length
                and self.fields is other.fields
                and self.field_values == other.field_values)

    def __repr__(self):
        """Produce a human-readable representation of this Keyspace and its
        current value.
        """
        enabled_field_idents = [
            i for (i, f) in self._enabled_fields()]

        return "<{}-bit Keyspace {}>".format(
            self.length,
            ", ".join("'{}':{}".format(identifier,
                                       self.field_values.get(identifier, "?"))
                      for identifier in enabled_field_idents))

    class Field(object):
        """Internally used class which defines a field.
        """

        def __init__(self, length=None, start_at=None, tags=None,
                     conditions=None, max_value=1):
            """Field definition used internally by
            :py:class:`~.spinnaker.keyspaces.Keyspace`.

            Parameters/Attributes
            ---------------------
            length : int
                The number of bits in the field. *None* if this should be
                determined based on the values assigned to it.
            start_at : int
                0-based index of least significant bit of the field within the
                keyspace.  *None* if this field is to be automatically placed
                into an unused area of the keyspace.
            tags : set
                A (possibly empty) set of tags used to classify the field.
            conditions : dict
                Specifies conditions when this field is valid. If empty, this
                field is always defined. Otherwise, keys in the dictionary
                specify field-identifers and values specify the desired value.
                All listed fields must match the specified values for the
                condition to be met.
            max_value : int
                The largest value ever assigned to this field (used for
                automatically determining field sizes.
            """
            self.length = length
            self.start_at = start_at
            self.tags = tags or set()
            self.conditions = conditions or dict()
            self.max_value = max_value

    def _assert_field_available(self, identifier, field_values=None):
        """Raise a human-readable ValueError if the specified field does not
        exist or is not enabled by the current field values.

        Parameters
        ----------
        identifier : str
            The field to check for availability.
        field_values : dict or None
            The values currently assigned to fields.
        """
        if field_values is None:
            field_values = self.field_values

        if identifier not in self.fields:
            raise AttributeError(
                "Field '{}' does not exist.".format(identifier))
        elif identifier not in (i for (i, f) in
                                self._enabled_fields(field_values)):
            # Accumulate the complete list of conditions which must be true for
            # the given field to exist
            unmet_conditions = []
            unchecked_fields = [identifier]
            while unchecked_fields:
                field = self.fields[unchecked_fields.pop(0)]
                for cond_identifier, cond_value in field.conditions.items():
                    actual_value = field_values.get(cond_identifier, None)
                    if actual_value != cond_value:
                        unmet_conditions.append((cond_identifier, cond_value))
                        unchecked_fields.append(cond_identifier)

            raise AttributeError("Field '{}' requires that {}.".format(
                identifier,
                ", ".join("'{}' == {}".format(cond_ident, cond_val)
                          for cond_ident, cond_val in unmet_conditions)))

    def _assert_tag_exists(self, tag):
        """Raise a human-readable ValueError if the supplied tag is not used by
        any enabled field.
        """

        for identifier, field in self._enabled_fields():
            if tag in field.tags:
                return
        raise ValueError("Tag '{}' does not exist.".format(tag))

    def _enabled_fields(self, field_values=None):
        """Generator of (identifier, field) tuples which iterates over the
        fields which can be set based on the currently specified field values.

        Parameters
        ----------
        field_values : dict or None
            Dictionary of field identifier to value mappings to use in the
            test. If *None*, uses `self.field_values`.
        """
        if field_values is None:
            field_values = self.field_values

        for identifier, field in self.fields.items():
            if not field.conditions or \
               all(field_values.get(cond_field, None) == cond_value
                   for cond_field, cond_value
                   in field.conditions.items()):
                yield (identifier, field)

    def _potential_fields(self, field_values=None):
        """Generator of (identifier, field) tuples iterating over every field
        which could potentially be defined given the currently specified field
        values.

        Parameters
        ----------
        field_values : dict or None
            Dictionary of field identifier to value mappings to use in the
            test. If *None*, uses `self.field_values`.
        """
        if field_values is None:
            field_values = self.field_values

        # Fields are blocked when their conditions can't be met. This only
        # occurs if a condition field's value can't be as the condition
        # requires. This can occur either because the user has already assigned
        # a value which doesn't mean the condition or the conditional field
        # itself has been blocked (and thus can't ever be set to meet the
        # condition). Since fields are partially ordered by hierarchy, we can
        # simply build up a set of blocked fields as we go and be guaranteed
        # to have already seen any field which appears in a condition.
        blocked = set()
        for identifier, field in self.fields.items():
            if not field.conditions \
               or all(cond_field not in blocked and
                      field_values.get(cond_field, cond_value) == cond_value
                      for cond_field, cond_value
                      in field.conditions.items()):
                yield (identifier, field)
            else:
                blocked.add(identifier)

    def _assign_enabled_fields(self):
        """For internal use only. Assign a position & length to any enabled
        fields which do not have one.
        """
        assigned_bits = 0
        unassigned_fields = []
        for identifier, field in self._enabled_fields():
            if field.length is not None and field.start_at is not None:
                assigned_bits |= ((1 << field.length) - 1) << field.start_at
            else:
                unassigned_fields.append((identifier, field))

        for identifier, field in unassigned_fields:
            length = field.length
            if length is None:
                # Assign lengths based on values
                length = int(log(field.max_value, 2)) + 1

            start_at = field.start_at
            if start_at is None:
                # Force a failure if no better space is found
                start_at = self.length

                # Try every position until a space is found
                for bit in range(0, self.length - length):
                    field_bits = ((1 << length) - 1) << bit
                    if not (assigned_bits & field_bits):
                        start_at = bit
                        assigned_bits |= field_bits
                        break

            # Check that the calculated field is within the Keyspace
            if start_at + length <= self.length:
                field.length = length
                field.start_at = start_at
            else:
                raise ValueError(
                    "{}-bit field '{}' "
                    "does not fit in keyspace.".format(
                        field.length, identifier))
