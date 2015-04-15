"""A system for defining and representing bit fields.

A common use-ase for this module is defining SpiNNaker routing keys based on
hierarchical bit-fields.

See the :py:class:`.BitField` class.
"""

from collections import namedtuple, OrderedDict

from math import log


class BitField(object):
    """Defines a hierarchical bit field and the values of those fields.

    Conceptually, a bit field is a sequence of bits which are logically broken
    up into individual fields which represent independent, unsigned integer
    values. For example, one could represent a pair of eight-bit values `x` and
    `y` as a sixteen-bit bit field where the upper eight bits are `x` and the
    lower eight bits are `y`. Bit fields are used when multiple pieces of
    information must be conveyed by a single binary value.

    For example, one method of allocating SpiNNaker routing keys (which are
    32-bit values) is to define each route a key as bit field with three
    fields. The fields `x`, `y`, and `p` can be used to represent the x- and
    y-chip-coordinate and processor id of a route's source.

    A hierarchical bit field is a bit field with fields which only exist
    dependent on the values of other fields. For a further routing-key related
    example, different key formats may be used by external devices and the rest
    of the SpiNNaker application. In these cases, a single bit could be used in
    the key to determine which key format is in use. Depending on the value of
    this bit, different fields would become available.

    This class supports the following key features:

    * Construction of guaranteed-safe hierarchical bit field formats.
    * Generation of bit-masks which select only defined fields
    * Automatic allocation of field sizes based on values actually used.
    * Partial-definition of a bit field (i.e. defining only a subset of
      available fields).
    """

    def __init__(self, length=32, _fields=None, _field_values=None):
        """Create a new BitField.

        An instance, `b`, of :py:class:`.BitField` represents a fixed-length
        hierarchical bit field with initially no fields. Fields can be added
        using :py:meth:`.BitField.add_field`. Derivatives of this instance
        with fields set to specific values can be created using the 'call'
        syntax: `b(field_name=value, other_field_name=other_value)` (see
        :py:meth:`.BitField.__call__`).

        .. Note::
            Only one :py:class:`.BitField` instance should be explicitly
            created for each bit field.

        Parameters
        ----------
        length : int
            The total number of bits in the bit field.
        _fields : dict
            For internal use only. The shared, global field dictionary.
        _field_values : dict
            For internal use only. Mapping of field-identifier to value.
        """
        self.length = length

        # An OrderedDict if field definitions (globally shared by all
        # derivatives of the same BitField) which maps human-friendly
        # field-identifiers (e.g.  strings) to corresponding BitField._Field
        # instances. An OrderedDict preserves insertion ordering which is used
        # to automatic field positioning more predictable and also ensures the
        # fields are stored under the partial ordering of their hierarchy (a
        # property used by this code).
        self.fields = _fields if _fields is not None else OrderedDict()

        if _field_values is not None:
            self.field_values = _field_values
        else:
            self.field_values = dict()

    def add_field(self, identifier, length=None, start_at=None, tags=None):
        """Add a new field to the BitField.

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
            The number of bits in the field. If None the field will be
            automatically assigned a length long enough for the largest value
            assigned.
        start_at : int or None
            0-based index of least significant bit of the field within the
            bit field. If None the field will be automatically located in free
            space in the bit field.
        tags : string or collection of strings or None
            A (possibly empty) set of tags used to classify the field.  Tags
            should be valid Python identifiers. If a string, the string must be
            a single tag or a space-separated list of tags. If *None*, an empty
            set of tags is assumed. These tags are applied recursively to all
            fields of which this field is a child.

        Raises
        ------
        ValueError
            If any the field overlaps with another one or does not fit within
            the bit field. Note that fields with unspecified lengths and
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

        # Check for fields which don't fit in the bit field
        if (start_at is not None and
            (0 <= start_at >= self.length or
             start_at + (length or 1) > self.length)):
            raise ValueError(
                "Field doesn't fit within {}-bit bit field.".format(
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
        self.fields[identifier] = BitField._Field(
            length, start_at, tags, dict(self.field_values))

    def __call__(self, **field_values):
        """Return a new BitField instance with fields assigned values as
        specified in the keyword arguments.

        Returns
        -------
        :py:class:`.BitField`
            A `BitField` derived from this one but with the specified fields
            assigned a value.

        Raises
        ------
        ValueError
            If any field has already been assigned a value or the value is too
            large for the field.
        AttributeError
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

        return type(self)(self.length, self.fields, field_values)

    def __getattr__(self, identifier):
        """Get the value of a field.

        Returns
        -------
        int or None
            The value of the field (or None if the field has not been given a
            value).

        Raises
        ------
        AttributeError
            If the field requested does not exist or is not available given
            current field values.
        """
        self._assert_field_available(identifier)
        return self.field_values.get(identifier, None)

    def get_value(self, tag=None, field=None):
        """Generate an integer whose bits are set according to the values of
        fields in this bit field. All bits not in a field are set to zero.

        Parameters
        ----------
        tag : str
            Optionally specifies that the value should only include fields with
            the specified tag.
        field : str
            Optionally specifies that the value should only include the
            specified field.

        Raises
        ------
        ValueError
            If a field whose length or position has not been defined. (i.e.
            `assign_fields()` has not been called when a field's
            length/position has not been fixed.
        """
        assert not (tag is not None and field is not None), \
            "Cannot filter by tag and field simultaneously."

        # Build a filtered list of fields to be used in the value
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
                "Cannot generate value with undefined fields {}.".format(
                    ", ".join(missing_fields_idents)))

        # Build the value
        value = 0
        for identifier in selected_field_idents:
            field = self.fields[identifier]
            if field.length is None or field.start_at is None:
                raise ValueError(
                    "Field '{}' does not have a fixed size/position.".format(
                        identifier))
            value |= (self.field_values[identifier] <<
                      field.start_at)

        return value

    def get_mask(self, tag=None, field=None):
        """Get the mask for all fields which exist in the current bit field.

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
        ValueError
            If a field whose length or position has not been defined. (i.e.
            `assign_fields()` has not been called when a field's size/position
            has not been fixed.
        """
        if tag is not None and field is not None:
            raise TypeError("get_mask() takes exactly one keyword argument, "
                            "either 'field' or 'tag' (both given)")

        # Build a filtered list of fields to be used in the mask
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

    def get_tags(self, field):
        """Get the set of tags for a given field.

        Parameters
        ----------
        field : str
            The field whose tag should be read.

        Returns
        -------
        set([tag, ...])
        """
        return self.fields[field].tags.copy()

    def assign_fields(self):
        """Assign a position & length to any fields which do not have one.

        Users should typically call this method after all field values have
        been assigned, otherwise fields may be fixed at an inadequate size.
        """
        # We must fix fields at every level of the hierarchy separately
        # (otherwise fields of children won't be allowed to overlap). Here we
        # do a breadth-first iteration over the hierarchy to fix fields with
        # given starting positions; then we do depth-first to fix other fields.
        #
        # The breadth-first ensures that children's fixed position fields must
        # fit around the fixed position fields of their parents.  The depth
        # first search for variable position fields ensures that parents don't
        # allocate fields in positions which would collide with fixed and
        # variable position fields their children have already allocated.

        class Node(namedtuple("Node", "bitfield children")):
            """Node used in depth-first search of bitfields."""
            def recurse_assign_unfixed_fields(self, assigned_bits=0,
                                              excluded_fields=set()):
                # Call this for the children first
                excludes = set(i for (i, f) in self.bitfield._enabled_fields())
                new_assigned_bits = assigned_bits
                for child in self.children:
                    # Children can assign bits independently
                    new_assigned_bits |= child.recurse_assign_unfixed_fields(
                        assigned_bits, excludes)

                # Now assign locally
                assigned_bits =\
                    self.bitfield._assign_enabled_fields_without_fixed_start(
                        new_assigned_bits, excluded_fields
                    )

                return assigned_bits

        root = Node(BitField(self.length, self.fields), list())
        unsearched_hierarchy = [root]

        # Build a tree of Node describing the bitfield hierarchy and assign all
        # fields with a fixed starting position.
        while unsearched_hierarchy:
            parent = unsearched_hierarchy.pop(0)
            ks = parent.bitfield

            # Assign all fields with a fixed starting position
            ks._assign_enabled_fields_with_fixed_start()

            # Look for potential children in the hierarchy
            for identifier, field in ks._potential_fields():
                enabled_field_idents = set(i for (i, f) in
                                           ks._enabled_fields())
                set_fields = {}

                for cond_ident, cond_value in field.conditions.items():
                    # Fail if not a child
                    if cond_ident not in enabled_field_idents:
                        set_fields = {}
                        break
                    # Accumulate fields which must be set
                    if getattr(ks, cond_ident) is None:
                        set_fields[cond_ident] = cond_value

                if set_fields:
                    child = Node(ks(**set_fields), list())
                    parent.children.append(child)
                    unsearched_hierarchy.append(child)

        # Assign all fields with variables starting positions
        root.recurse_assign_unfixed_fields()

    def __eq__(self, other):
        """Test that this :py:class:`.BitField` is equivalent to another.

        In order to be equal, the other :py:class:`.BitField` must be a
        descendent of the same original :py:class:`.BitField` (and thus will
        *always* have exactly the same set of fields). It must also have the
        same field values defined.
        """
        return (self.length == other.length and
                self.fields is other.fields and
                self.field_values == other.field_values)

    def __repr__(self):
        """Produce a human-readable representation of this bit field and its
        current value.
        """
        enabled_field_idents = [
            i for (i, f) in self._enabled_fields()]

        return "<{}-bit BitField {}>".format(
            self.length,
            ", ".join("'{}':{}".format(identifier,
                                       self.field_values.get(identifier, "?"))
                      for identifier in enabled_field_idents))

    class _Field(object):
        """Internally used class which defines a field.
        """

        def __init__(self, length=None, start_at=None, tags=None,
                     conditions=None, max_value=1):
            """Field definition used internally by :py:class:`.BitField`.

            Parameters/Attributes
            ---------------------
            length : int
                The number of bits in the field. *None* if this should be
                determined based on the values assigned to it.
            start_at : int
                0-based index of least significant bit of the field within the
                bit field.  *None* if this field is to be automatically placed
                into an unused area of the bit field.
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
        """Raise a human-readable :py:exc:`ValueError` if the specified field
        does not exist or is not enabled by the current field values.

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
        """Raise a human-readable :py:exc:`ValueError` if the supplied tag is
        not used by any enabled field.
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
            test. If None, uses `self.field_values`.
        """
        if field_values is None:
            field_values = self.field_values

        for identifier, field in self.fields.items():
            if not field.conditions or \
               all(field_values.get(cond_field, None) == cond_value
                   for cond_field, cond_value
                   in field.conditions.items()):
                yield (identifier, field)

    def _potential_fields(self):
        """Generator of (identifier, field) tuples iterating over every field
        which could potentially be defined given the currently specified field
        values.
        """
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
                      self.field_values.get(cond_field, cond_value) ==
                      cond_value
                      for cond_field, cond_value
                      in field.conditions.items()):
                yield (identifier, field)
            else:
                blocked.add(identifier)

    def _assign_enabled_fields_with_fixed_start(self):
        """For internal use only. Assign a length to any enabled fields which
        do not have one but do have a fixed position.
        """
        assigned_bits = 0
        unassigned_fields = list()
        for identifier, field in self._enabled_fields():
            if field.length is not None and field.start_at is not None:
                assigned_bits |= ((1 << field.length) - 1) << field.start_at
            elif field.start_at is not None:
                unassigned_fields.append((identifier, field))

        for identifier, field in unassigned_fields:
            assigned_bits = self._assign_enabled_field(
                assigned_bits, identifier, field)

    def _assign_enabled_fields_without_fixed_start(self, assigned_bits,
                                                   exclude_fields=set()):
        """For internal use only. Assign a length and position to any enabled
        fields which do not have a fixed position.

        Parameters
        ----------
        exclude_fields : {identifier, ...}
            Exclude fields which will be assigned later, for example those
            which will be assigned by bitfields higher up the hierarchy.

        Returns
        -------
        int
            Mask of which bits have been assigned to fields.
        """
        unassigned_fields = list()
        for identifier, field in self._enabled_fields():
            if field.length is None or field.start_at is None:
                if identifier not in exclude_fields:
                    unassigned_fields.append((identifier, field))
            else:
                assigned_bits |= ((1 << field.length) - 1) << field.start_at

        for identifier, field in unassigned_fields:
            assert identifier not in exclude_fields
            assigned_bits |= self._assign_enabled_field(
                assigned_bits, identifier, field)

        return assigned_bits

    def _assign_enabled_field(self, assigned_bits, identifier, field):
        """For internal use only.  Assign a length and position to a field
        which may have either one of these values missing.

        Returns
        -------
        int
            Mask of which bits have been assigned to fields.
        """
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
        else:
            # A start position has been forced, ensure that it can be fulfilled
            field_bits = ((1 << length) - 1) << start_at

            if assigned_bits & field_bits:
                raise ValueError(
                    "{}-bit field '{}' with fixed position does not fit in "
                    "bit field.".format(
                        field.length, identifier)
                )

            # Mark these bits as assigned
            assigned_bits |= field_bits

        # Check that the calculated field is within the bit field
        if start_at + length <= self.length:
            field.length = length
            field.start_at = start_at
        else:
            raise ValueError(
                "{}-bit field '{}' does not fit in bit field.".format(
                    field.length, identifier)
            )

        return assigned_bits
