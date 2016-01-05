.. py:module:: rig.routing_table

:py:mod:`rig.routing_table`: Multicast routing table datastructures and tools
=============================================================================

This module contains data structures and algorithms for representing and
manipulating multicast routing tables for SpiNNaker.

:py:class:`.RoutingTableEntry` and :py:class:`.Routes`: Routing table data structures
-------------------------------------------------------------------------------------

.. autoclass:: rig.routing_table.RoutingTableEntry
    :members:

.. autoclass:: rig.routing_table.Routes
    :members:


Routing table minimisation algorithms
-------------------------------------

SpiNNaker's multicast routing tables are a finite resource containing a maximum
of 1024 entries. Certain applications may find that they exhaust this limited
resource when naively producing routing tables using functions such as
:py:func:`rig.place_and_route.utils.build_routing_tables`. By more fully
exploiting the behaviour of the Ternary Content Addressable Memory (TCAM) used
in SpiNNaker's multicast router it is often possible to compress (or minimise)
a given routing table into a more compact, yet logically equivalent, form.

This module includes algorithms for minimising routing tables for use by
SpiNNaker application developers. It also includes tools for verifying the
equivalence of routing tables to aid developers of new routing table
minimisation algorithms.

All routing table minimisation functions expose the following common API. A
sensible default algorithm is aliased under the name
:py:func:`rig.routing_table.minimise`.

:py:func:`.minimise` prototype
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. py:function:: minimise(routing_table, target_length=1024)
    
    Reduce the size of a routing table by merging together entries where
    possible.

    .. warning::

        The input routing table *must* also include entries which could be
        removed and replaced by default routing.

    .. warning::

        It is assumed that the input routing table is not in any particular
        order and may be reordered into ascending order of generality (number
        of don't cares/Xs in the key-mask) without affecting routing
        correctness.  It is also assumed that if this table is unordered it is
        at least orthogonal (i.e., there are no two entries which would match
        the same key) and reorderable.

        .. note::

            If *all* the keys in the table are derived from a single instance
            of :py:class:`~rig.bitfield.BitField` then the table is guaranteed
            to be orthogonal and reorderable.

        .. note::

            Use :py:meth:`~rig.routing_table.expand_entries` to generate an
            orthogonal table and receive warnings if the input table is not
            orthogonal.

    Parameters
    ----------
    routing_table : [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
        Routing entries to be merged.

    Other Parameters
    ----------------
    target_length : int or None
        If an int, this is the target length of the routing table; the
        minimisation procedure may halt once either this target is reached or
        no further minimisation is possible. If the target could not be reached
        a :py:exc:`.MinimisationFailedError` will be raised.
        
        If None then the table will be made as small as possible and is
        guaranteed to return a result.

    Raises
    ------
    MinimisationFailedError
        If the smallest table that can be produced is larger than
        ``target_length`` and ``target_length`` is not None.

    Returns
    -------
    [:py:class:`~rig.routing_table.RoutingTableEntry`, ...]
        Reduced routing table entries. The returned routing table is guaranteed
        to route all entries matched by the input table in the same way. Note
        that the minimised table may also match keys *not* previously matched
        by the input routing table.

.. autoexception:: rig.routing_table.MinimisationFailedError

Example usage
~~~~~~~~~~~~~

The brief example below illustrates how a single routing table might be
minimised.

.. doctest::

    >>> # Define a (trivially minimised) example routing table
    >>> from rig.routing_table import Routes, RoutingTableEntry
    >>> original = [
    ...     RoutingTableEntry({Routes.north}, 0x00000000, 0xFFFFFFFF),
    ...     RoutingTableEntry({Routes.north}, 0x00000001, 0xFFFFFFFF),
    ...     RoutingTableEntry({Routes.north}, 0x00000002, 0xFFFFFFFF),
    ...     RoutingTableEntry({Routes.north}, 0x00000003, 0xFFFFFFFF),
    ... ]

    >>> # Minimise the routing table as much as possible
    >>> from rig.routing_table import minimise
    >>> minimised = minimise(original, target_length=None)
    >>> assert minimised == [
    ...     RoutingTableEntry({Routes.north}, 0x00000000, 0xFFFFFFFC),
    ... ]

.. note::

    In real world applications where the Rig place-and-route tools are being
    used the
    :py:func:`rig.place_and_route.utils.build_and_minimise_routing_tables`
    utility function internally does something similar to this example.

Available algorithms
~~~~~~~~~~~~~~~~~~~~

The following minimisation algorithms are currently available:

.. toctree::
    :maxdepth: 1
    
    routing_table_minimisation_algorithms/ordered_covering

Routing Table Manipulation Tools
--------------------------------

.. autofunction:: rig.routing_table.expand_entries

.. autofunction:: rig.routing_table.table_is_subset_of
