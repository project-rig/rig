import collections
from rig.routing_table import MinimisationFailedError
from rig.routing_table.remove_default_routes import minimise as \
    remove_default_entries
from rig.routing_table.ordered_covering import minimise as ordered_covering
from six import iteritems


def minimise_tables(routing_tables, target_lengths,
                    methods=(remove_default_entries, ordered_covering)):
    """Utility function which attempts to minimises routing tables for multiple
    chips.

    For each routing table supplied, this function will attempt to use the
    minimisation algorithms given (or some sensible default algorithms), trying
    each sequentially until a target number of routing entries has been
    reached.

    Parameters
    ----------
    routing_tables : {(x, y): [\
            :py:class:`~rig.routing_table.RoutingTableEntry`, ...], ...}
        Dictionary mapping chip co-ordinates to the routing tables associated
        with that chip. NOTE: This is the data structure as returned by
        :py:meth:`~rig.routing_table.routing_tree_to_tables`.
    target_lengths : int or {(x, y): int or None, ...} or None
        Maximum length of routing tables. If an integer this is assumed to be
        the maximum length for any table; if a dictionary then it is assumed to
        be a mapping from co-ordinate to maximum length (or None); if None then
        tables will be minimised as far as possible.
    methods :
        Each method is tried in the order presented and the first to meet the
        required target length for a given chip is used. Consequently less
        computationally costly algorithms should be nearer the start of the
        list. The defaults will try to remove default routes
        (:py:meth:`rig.routing_table.remove_default_routes.minimise`) and then
        fall back on the ordered covering algorithm
        (:py:meth:`rig.routing_table.ordered_covering.minimise`).

    Returns
    -------
    {(x, y): [:py:class:`~rig.routing_table.RoutingTableEntry`, ...], ...}
        Minimised routing tables, guaranteed to be at least as small as the
        table sizes specified by `target_lengths`.

    Raises
    ------
    MinimisationFailedError
        If no method can sufficiently minimise a table.
    """
    # Coerce the target lengths into the correct forms
    if not isinstance(target_lengths, dict):
        lengths = collections.defaultdict(lambda: target_lengths)
    else:
        lengths = target_lengths

    # Minimise the routing tables
    new_tables = dict()
    for chip, table in iteritems(routing_tables):
        # Try to minimise the table
        try:
            new_table = minimise_table(table, lengths[chip], methods)
        except MinimisationFailedError as exc:
            exc.chip = chip
            raise

        # Store the table if it isn't empty
        if new_table:
            new_tables[chip] = new_table

    return new_tables


def minimise_table(table, target_length,
                   methods=(remove_default_entries, ordered_covering)):
    """Apply different minimisation algorithms to minimise a single routing
    table.

    Parameters
    ----------
    table : [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
        Routing table to minimise.  NOTE: This is the data structure as
        returned by :py:meth:`~rig.routing_table.routing_tree_to_tables`.
    target_length : int or None
        Maximum length of the routing table. If None then all methods will be
        tried and the smallest achieved table will be returned.
    methods :
        Each method is tried in the order presented and the first to meet the
        required target length for a given chip is used. Consequently less
        computationally costly algorithms should be nearer the start of the
        list. The defaults will try to remove default routes
        (:py:meth:rig.routing_table.remove_default_routes.minimise) and then
        fall back on the ordered covering algorithm
        (:py:meth:rig.routing_table.ordered_covering.minimise).

    Returns
    -------
    [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
        Minimised routing table, guaranteed to be at least as small as
        `target_length`, or as small as possible if `target_length` is None.

    Raises
    ------
    MinimisationFailedError
        If no method can sufficiently minimise the table.
    """
    # Add a final method which checks the size of the table and returns it if
    # the size is correct. NOTE: This method will avoid running any other
    # minimisers if the table is already sufficiently small.
    methods = list(methods)
    methods.insert(0, _identity)

    if target_length is not None:
        best_achieved = len(table)

        # Try each minimiser in turn until the table is small enough
        for f in methods:
            try:
                # Minimise the table, if this fails a MinimisationFailedError
                # will be raised and the return will not be executed.
                new_table = f(table, target_length)
                return new_table
            except MinimisationFailedError as exc:
                # Store the best achieved final length
                if best_achieved is None or exc.final_length < best_achieved:
                    best_achieved = exc.final_length

        # The table must still be too large
        raise MinimisationFailedError(target_length, best_achieved)
    else:
        # Try all methods and return the smallest table
        return min((f(table, target_length) for f in methods), key=len)


def _identity(table, target_length):
    """Identity minimisation function."""
    if target_length is None or len(table) < target_length:
        return table
    raise MinimisationFailedError(target_length, len(table))
