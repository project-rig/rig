import warnings

from rig.routing_table import RoutingTableEntry


def table_is_subset_of(entries_a, entries_b):
    """Check that every key matched by every entry in one table results in the
    same route when checked against the other table.

    For example, the table::

        >>> from rig.routing_table import Routes
        >>> table = [
        ...     RoutingTableEntry({Routes.north, Routes.north_east}, 0x0, 0xf),
        ...     RoutingTableEntry({Routes.east}, 0x1, 0xf),
        ...     RoutingTableEntry({Routes.south_west}, 0x5, 0xf),
        ...     RoutingTableEntry({Routes.north, Routes.north_east}, 0x8, 0xf),
        ...     RoutingTableEntry({Routes.east}, 0x9, 0xf),
        ...     RoutingTableEntry({Routes.south_west}, 0xe, 0xf),
        ...     RoutingTableEntry({Routes.north, Routes.north_east}, 0xc, 0xf),
        ...     RoutingTableEntry({Routes.south, Routes.south_west}, 0x0, 0xb),
        ... ]

    is a functional subset of a minimised version of itself::

        >>> from rig.routing_table import minimise
        >>> other_table = minimise(table, target_length=None)
        >>> other_table == table
        False
        >>> table_is_subset_of(table, other_table)
        True

    But not vice-versa::

        >>> table_is_subset_of(other_table, table)
        False

    Parameters
    ----------
    entries_a : [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
    entries_b : [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
        Ordered of lists of routing table entries to compare.

    Returns
    -------
    bool
        True if every key matched in `entries_a` would result in an equivalent
        route for the packet when matched in `entries_b`.
    """
    # Determine which bits we don't need to explicitly test for
    common_xs = get_common_xs(entries_b)

    # For every entry in the first table
    for entry in expand_entries(entries_a, ignore_xs=common_xs):
        # Look at every entry in the second table
        for other_entry in entries_b:
            # If the first entry matches the second
            if other_entry.mask & entry.key == other_entry.key:
                if other_entry.route == entry.route:
                    # If the route is the same then we move on to the next
                    # entry in the first table.
                    break
                else:
                    # Otherwise we return false as the tables are different
                    return False
        else:
            # If we didn't break out of the loop then the entry from the first
            # table never matched an entry in the second table
            return False

    return True


def expand_entry(entry, ignore_xs=0x0):
    """Turn all Xs which are not marked in `ignore_xs` into ``0``\ s and
    ``1``\ s.

    The following will expand any Xs in bits ``1..3``\ ::

        >>> entry = RoutingTableEntry(set(), 0b0100, 0xfffffff0 | 0b1100)
        >>> list(expand_entry(entry, 0xfffffff1)) == [
        ...     RoutingTableEntry(set(), 0b0100, 0xfffffff0 | 0b1110),  # 010X
        ...     RoutingTableEntry(set(), 0b0110, 0xfffffff0 | 0b1110),  # 011X
        ... ]
        True

    Parameters
    ----------
    entry : :py:class:`~rig.routing_table.RoutingTableEntry` or similar
        The entry to expand.
    ignore_xs : int
        Bit-mask of Xs which should not be expanded.

    Yield
    -----
    :py:class:`~rig.routing_table.RoutingTableEntry`
        Routing table entries which represent the original entry but with all
        Xs not masked off by `ignore_xs` replaced with 1s and 0s.
    """
    # Get all the Xs in the entry that are not ignored
    xs = (~entry.key & ~entry.mask) & ~ignore_xs

    # Find the most significant X
    for bit in (1 << i for i in range(31, -1, -1)):
        if bit & xs:
            # Yield all the entries with this bit set as 0
            entry_0 = RoutingTableEntry(entry.route, entry.key,
                                        entry.mask | bit)
            for new_entry in expand_entry(entry_0, ignore_xs):
                yield new_entry

            # And yield all the entries with this bit set as 1
            entry_1 = RoutingTableEntry(entry.route, entry.key | bit,
                                        entry.mask | bit)
            for new_entry in expand_entry(entry_1, ignore_xs):
                yield new_entry

            # Stop looking for Xs
            break
    else:
        # If there are no Xs then yield the entry we were given.
        yield entry


def expand_entries(entries, ignore_xs=None):
    """Turn all Xs which are not ignored in all entries into ``0`` s and
    ``1`` s.

    For example::

        >>> from rig.routing_table import RoutingTableEntry
        >>> entries = [
        ...     RoutingTableEntry(set(), 0b0100, 0xfffffff0 | 0b1100),  # 01XX
        ...     RoutingTableEntry(set(), 0b0010, 0xfffffff0 | 0b0010),  # XX1X
        ... ]
        >>> list(expand_entries(entries)) == [
        ...     RoutingTableEntry(set(), 0b0100, 0xfffffff0 | 0b1110),  # 010X
        ...     RoutingTableEntry(set(), 0b0110, 0xfffffff0 | 0b1110),  # 011X
        ...     RoutingTableEntry(set(), 0b0010, 0xfffffff0 | 0b1110),  # 001X
        ...     RoutingTableEntry(set(), 0b1010, 0xfffffff0 | 0b1110),  # 101X
        ...     RoutingTableEntry(set(), 0b1110, 0xfffffff0 | 0b1110),  # 111X
        ... ]
        True

    Note that the ``X`` in the LSB was retained because it is common to all
    entries.

    Any duplicated entries will be removed (in this case the first and second
    entries will both match ``0000``, so when the second entry is expanded only
    one entry is retained)::

        >>> entries = [
        ...     RoutingTableEntry(0, 0b0000, 0b1111),  # 0000 -> 0
        ...     RoutingTableEntry(1, 0b0000, 0b1011),  # 0X00 -> 1
        ... ]
        >>> list(expand_entries(entries)) == [
        ...     RoutingTableEntry(0, 0b0000, 0b1111),  # 0000 -> 0
        ...     RoutingTableEntry(1, 0b0100, 0b1111),  # 0100 -> 1
        ... ]
        True

    .. warning::

        It is assumed that the input routing table is orthogonal (i.e., there
        are no two entries which would match the same key). If this is not the
        case, any entries which are covered (i.e. unreachable) in the input
        table will be omitted and a warning produced. As a result, all output
        routing tables are guaranteed to be orthogonal.

    Parameters
    ----------
    entries : [:py:class:`~rig.routing_table.RoutingTableEntry`...] or similar
        The entries to expand.

    Other Parameters
    ----------------
    ignore_xs : int
        Mask of bits in which Xs should not be expanded. If None (the default)
        then Xs which are common to all entries will not be expanded.

    Yield
    -----
    :py:class:`~rig.routing_table.RoutingTableEntry`
        Routing table entries which represent the original entries but with all
        Xs not masked off by `ignore_xs` replaced with 1s and 0s.
    """
    # Find the common Xs for the entries
    if ignore_xs is None:
        ignore_xs = get_common_xs(entries)

    # Keep a track of keys that we've seen
    seen_keys = set({})

    # Expand each entry in turn
    for entry in entries:
        for new_entry in expand_entry(entry, ignore_xs):
            if new_entry.key in seen_keys:
                # We've already used this key, warn that the table is
                # over-complete.
                warnings.warn("Table is not orthogonal: Key {:#010x} matches "
                              "multiple entries.".format(new_entry.key))
            else:
                # Mark the key as seen and yield the new entry
                seen_keys.add(new_entry.key)
                yield new_entry


def get_common_xs(entries):
    """Return a mask of where there are Xs in all routing table entries.

    For example ``01XX`` and ``XX1X`` have common Xs in the LSB only, for this
    input this method would return ``0b0001``::

        >>> from rig.routing_table import RoutingTableEntry
        >>> entries = [
        ...     RoutingTableEntry(None, 0b0100, 0xfffffff0 | 0b1100),  # 01XX
        ...     RoutingTableEntry(None, 0b0010, 0xfffffff0 | 0b0010),  # XX1X
        ... ]
        >>> print("{:#06b}".format(get_common_xs(entries)))
        0b0001
    """
    # Determine where there are never 1s in the key and mask
    key = 0x00000000
    mask = 0x00000000

    for entry in entries:
        key |= entry.key
        mask |= entry.mask

    # Where there are never 1s in the key or the mask there are Xs which are
    # common to all entries.
    return (~(key | mask)) & 0xffffffff
