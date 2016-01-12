from rig.routing_table import MinimisationFailedError
from rig.routing_table.utils import intersect


def minimise(table, target_length):
    """Remove from the routing table any entries which could be replaced by
    default routing.

    Parameters
    ----------
    routing_table : [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
        Routing table from which to remove entries which could be handled by
        default routing.
    target_length : int or None
        Target length of the routing table.

    Raises
    ------
    MinimisationFailedError
        If the smallest table that can be produced is larger than
        `target_length`.

    Returns
    -------
    [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
        Reduced routing table entries.
    """
    new_table = list()

    for i, entry in enumerate(table):
        if not _is_defaultable(i, entry, table):
            # If the entry cannot be removed then add it to the table
            new_table.append(entry)

    # If the resultant table is larger than the target raise an exception
    if target_length is not None and target_length < len(new_table):
        raise MinimisationFailedError(target_length, len(new_table))

    return new_table


def _is_defaultable(i, entry, table):
    """Determine if an entry may be removed from a routing table and be
    replaced by a default route.

    Parameters
    ----------
    i : int
        Position of the entry in the table
    entry : RoutingTableEntry
        The entry itself
    table : [RoutingTableEntry, ...]
        The table containing the entry.
    """
    # May only have one source and sink (which may not be None)
    if (len(entry.sources) == 1 and
            len(entry.route) == 1 and
            None not in entry.sources):
        # Neither the source nor sink may be a core
        source = next(iter(entry.sources))
        sink = next(iter(entry.route))

        if source.is_link and sink.is_link:
            # The source must be going in the same direction as the link
            if source.opposite is sink:
                # And the entry must not be aliased
                key, mask = entry.key, entry.mask
                if not any(intersect(key, mask, d.key, d.mask) for
                           d in table[i+1:]):
                    return True
    return False
