.. py:module:: rig.routing_table

:py:mod:`rig.routing_table`: Multicast routing table datastructures and tools
=============================================================================

This module contains data structures and algorithms for representing and
manipulating multicast routing tables for SpiNNaker.

Quick-start Examples
--------------------

The following examples give quick examples of Rig's routing table data
structures and table minimisation tools.

Using the place-and-route wrapper
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're using the :py:func:`~rig.place_and_route.place_and_route_wrapper`
wrapper function to perform place-and-route for your application, routing table
minimisation is performed automatically when required. No changes are required
to your application!

Manually defining and minimising individual routing tables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The brief example below illustrates how a single routing table might be
defined and minimised.

.. doctest::

    >>> # Define a (trivially minimised) example routing table
    >>> from rig.routing_table import Routes, RoutingTableEntry
    >>> original = [
    ...     RoutingTableEntry({Routes.north}, 0x00000000, 0xFFFFFFFF),
    ...     RoutingTableEntry({Routes.north}, 0x00000001, 0xFFFFFFFF),
    ...     RoutingTableEntry({Routes.north}, 0x00000002, 0xFFFFFFFF),
    ...     RoutingTableEntry({Routes.north}, 0x00000003, 0xFFFFFFFF),
    ... ]

    >>> # Minimise the routing table using a sensible selection of algorithms
    >>> from rig.routing_table import minimise_table
    >>> minimised = minimise_table(original, target_length=None)
    >>> assert minimised == [
    ...     RoutingTableEntry({Routes.north}, 0x00000000, 0xFFFFFFFC),
    ... ]

Generating and loading routing tables from automatic place-and-route tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The outline below shows how routing tables might be generated from the results
of Rig's :py:mod:`place and route <rig.place_and_route>` tools, minimised and
then loaded onto a SpiNNaker machine.

.. code-block:: python

    # Interrogate the SpiNNaker machine to determine what resources are
    # available (including the number of multicast routing table entries on
    # each chip).
    from rig.machine_control import MachineController
    machine_controller = MachineController("hostname")
    system_info = machine_controller.get_system_info()
    
    # Place-and-route your application as normal and select suitable
    # routing keys for each net.
    from rig.place_and_route import route
    routes = route(...)
    net_keys = {Net: (key, mask), ...}
    
    # Produce routing tables from the generated routes
    from rig.routing_table import routing_tree_to_tables
    routing_tables = routing_tree_to_tables(routes, net_keys)
    
    # Minimise the routes (if required), trying a sensible selection of table
    # minimisation algorithms.
    from rig.routing_table import (
        build_routing_table_target_lengths,
        minimise_tables)
    target_lengths = build_routing_table_target_lengths(system_info)
    routing_tables = minimise_tables(routing_tables, target_lengths)

    # Load the minimised routing tables onto SpiNNaker
    machine_controller.load_routing_tables(routing_tables)


:py:class:`.RoutingTableEntry` and :py:class:`.Routes`: Routing table data structures
-------------------------------------------------------------------------------------

Routing tables in Rig are conventionally represented as a list of
:py:class:`~rig.routing_table.RoutingTableEntry` objects in the order they
would appear in a SpiNNaker router. Empty/unused routing table entries are not
usually included in these representations.

.. autoclass:: rig.routing_table.RoutingTableEntry
    :members:

.. autoclass:: rig.routing_table.Routes
    :members:

Routing table construction utility
----------------------------------

The :py:func:`~rig.routing_table.routing_tree_to_tables` function is provided
which constructs routing tables of the form described above from
:py:class:`~rig.place_and_route.routing_tree.RoutingTree` objects produced by an automatic
routing algorithm.

.. autofunction:: rig.routing_table.routing_tree_to_tables

.. autoexception:: rig.routing_table.MultisourceRouteError

Routing table minimisation algorithms
-------------------------------------

SpiNNaker's multicast routing tables are a finite resource containing a maximum
of 1024 entries. Certain applications may find that they exhaust this limited
resource and may wish to attempt to shrink their routing tables by making
better use of the SpiNNaker router's capabilities. For example, if a packet's
key does not match any routing entries it will be "default routed" in the
direction in which it was already travelling and thus no routing table entry is
required.  Additionally, by more fully exploiting the behaviour of the Ternary
Content Addressable Memory (TCAM) used in SpiNNaker's multicast router it is
often possible to compress (or minimise) a given routing table into a more
compact, yet logically equivalent, form.

This module includes algorithms for minimising routing tables for use by
SpiNNaker application developers. 

Common-case wrappers
~~~~~~~~~~~~~~~~~~~~

For most users, the following functions can be used to minimise routing tables
used by their application. Both accept a target number of routing entries and
will attempt to apply routing table minimisation algorithms from this module
until the supplied tables fit.

.. autofunction:: rig.routing_table.minimise_tables

.. autofunction:: rig.routing_table.minimise_table


Available algorithms
~~~~~~~~~~~~~~~~~~~~

The following minimisation algorithms are currently available:

.. toctree::
    :maxdepth: 1
    
    routing_table_minimisation_algorithms/remove_default_routes
    routing_table_minimisation_algorithms/ordered_covering

:py:func:`.minimise` prototype
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Routing table minimisation functions are always named ``minimise()`` and are
contained within a Python module named after the algorithm. These
:py:func:`.minimise` functions have the signature defined below.

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

Routing Table Manipulation Tools
--------------------------------

The following functions may be useful when comparing routing tables, for
example if testing or evaluating minimisation algorithms.

.. autofunction:: rig.routing_table.table_is_subset_of

.. autofunction:: rig.routing_table.expand_entries

.. autofunction:: rig.routing_table.intersect

Utility Functions
-----------------

.. autofunction:: rig.routing_table.build_routing_table_target_lengths
