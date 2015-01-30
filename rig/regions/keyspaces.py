from six import iteritems
import struct
from .region import Region, PrependedValue


class KeyspacesRegion(Region):
    """A region of memory which represents data formed from a list of
    :py:class:`~rig.keyspaces.Keyspace` instances.

    Each "row" represents a keyspace, and each "column" is formed by getting
    the result of a function applied to the keyspace.  Each field will be the
    same size, the smallest number of bytes required to represent the keyspace.
    For example, if 12 bit keyspaces were used each field would be 2 bytes
    long.
    """
    def __init__(self, keyspaces, fields=list(), partitioned_by_atom=False,
                 prepends=list()):
        """Create a new region representing Keyspace information.

        Parameters
        ----------
        keyspaces : iterable
            An iterable containing instances of
            :py:class:`~rig.keyspaces.Keyspace`
        fields : iterable
            An iterable of callables which will be called on each key and must
            return an appropriate sized bytestring representing the data to
            write to memory.  The appropriate size is the number of bytes
            required to represent a full key or mark (e.g., 4 bytes for 32 bit
            keyspaces).
        partitioned_by_atom : bool
            If True then one set of fields will be written out per atom, if
            False then fields for all keyspaces are written out regardless of
            the vertex slice.
        prepends : list of :py:class:`RegionPrepend`
            Values which will be prepended to the keyspace fields when they are
            written out into memory.
        """
        super(KeyspacesRegion, self).__init__(prepends=prepends)

        # Save the keyspaces, fields and partitioned status
        self.keyspaces = keyspaces[:]
        self.fields = fields[:]
        self.partitioned = partitioned_by_atom

        # Determine the number of bytes per field
        max_bits = max(ks.length for ks in self.keyspaces)
        self.bytes_per_field = (max_bits >> 3) + (1 if max_bits & 0x7 != 0
                                                  else 0)

    def sizeof(self, vertex_slice):
        """Get the size of a slice of this region in bytes.

        See :py:method:`Region.sizeof`
        """
        # Get the memory requirements of the prepends
        pp_size = super(KeyspacesRegion, self).sizeof(vertex_slice)

        # Get the size from representing the fields
        if not self.partitioned:
            n_keys = len(self.keyspaces)
        else:
            assert vertex_slice.stop < len(self.keyspaces) + 1
            n_keys = vertex_slice.stop - vertex_slice.start

        return self.bytes_per_field * n_keys * len(self.fields) + pp_size

    def write_subregion_to_file(self, vertex_slice, fp, **field_args):
        """Write the data contained in a portion of this region out to file.
        """
        # Get a slice onto the keys
        if self.partitioned:
            assert vertex_slice.stop < len(self.keyspaces) + 1
        key_slice = vertex_slice if self.partitioned else slice(None)

        # Write out the prepends
        super(KeyspacesRegion, self).write_subregion_to_file(vertex_slice, fp,
                                                            **field_args)

        # Get the size of the data to write
        c = {1: 'B', 2: 'H', 4: 'I'}[self.bytes_per_field]

        # For each key fill in each field
        data = b''
        for ks in self.keyspaces[key_slice]:
            for field in self.fields:
                data += struct.pack("<{}".format(c), field(ks, **field_args))

        # Write out
        fp.write(data)


class PrependNumKeyspaces(PrependedValue):
    """Prepend the number of keyspaces that are in the region."""
    def __init__(self, n_bytes=4):
        super(PrependNumKeyspaces, self).__init__(n_bytes, signed=False)

    def _get_prepended_value(self, vertex_slice, region):
        """Get the prepended value, in this case the number of keyspaces that
        are contained in the given slice.
        """
        if region.partitioned:
            return vertex_slice.stop - vertex_slice.start
        else:
            return len(region.keyspaces)


# NOTE: This closure intentionally tries to look like a class.
# TODO: Neaten this docstring.
def KeyField(maps={}, field=None, tag=None):
    """Create new field for a :py:class:`~KeyspacesRegion` that will fill in
    specified fields of the key and will then write out a key.

    Parameters
    ----------
    maps : dict
        A mapping from keyword-argument of the field to the field of the key
        that this value should be inserted into.
    field : string or None
        The field to get the key or None for all fields.

    For example:

        ks = Keyspace()
        ks.add_field(i)
        # ...

        kf = KeyField(maps={'subvertex_index': 'i'})
        k = Keyspace()
        kf(k, subvertex_index=11)

    Will return the key with the 'i' key set to 11.
    """
    key_field = field

    def key_getter(keyspace, **kwargs):
        # Build a set of fields to fill in
        fills = {}
        for (kwarg, field) in iteritems(maps):
            fills[field] = kwargs[kwarg]

        # Build the key with these fills made
        key = keyspace(**fills)

        return key.get_key(field=key_field, tag=tag)

    return key_getter


# NOTE: This closure intentionally tries to look like a class.
def MaskField(**kwargs):
    """Create a new field for a :py:class:`~.KeyspacesRegion` that will write
    out a mask value from a keyspace.

    Parameters
    ----------
    field : string
        The name of the keyspace field to store the mask for.
    tag : string
        The name of the keyspace tag to store the mask for.

    Raises
    ------
    TypeError
        If both or neither field and tag are specified.

    Returns
    -------
    function
        A function which can be used in the `fields` argument to
        :py:class:`~.KeyspacesRegion` that will include a specified mask in the
        region data.
    """
    # Process the arguments
    field = kwargs.get("field")
    tag = kwargs.get("tag")

    # Create the field method
    if field is not None and tag is None:
        def mask_getter(keyspace, **kwargs):
            return keyspace.get_mask(field=field)

        return mask_getter
    elif tag is not None and field is None:
        def mask_getter(keyspace, **kwargs):
            return keyspace.get_mask(tag=tag)

        return mask_getter
    else:
        raise TypeError("MaskField expects 1 argument, "
                        "either 'field' or 'tag'.")
