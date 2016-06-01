Place and route
===============

.. doctest::

    >>> import random
    >>> from rig.place_and_route import place_and_route_wrapper, Cores, SDRAM
    >>> from rig.netlist import Net
    >>> from rig.machine_control import MachineController
    
    >>> # Define a graph with 50 vertices and random 100 multicast nets.
    >>> vertices = [object() for _ in range(50)]
    >>> vertices_resources = {
    ...     vertex: {Cores: 1, SDRAM: 10 * 1024 * 1024}
    ...     for vertex in vertices
    ... }
    >>> nets = [Net(random.choice(vertices), random.sample(vertices, 4))
    ...         for _ in range(100)]
    >>> vertices_applications = {vertex: "my_app.aplx" for vertex in vertices}
    >>> net_keys = {net: (number, 0xFFFFFFFF) for number, net in enumerate(nets)}
    
    >>> # Interrogate the SpiNNaker machine to determine its topology etc.
    >>> system_info = MachineController("hostname-or-ip").get_system_info()
    
    >>> # Place, route and generate routing tables.
    >>> placements, allocations, application_map, routing_tables = \
    ...     place_and_route_wrapper(vertices_resources, vertices_applications,
    ...                             nets, net_keys, system_info)

Reference:

* :py:mod:`rig.place_and_route`
* :py:func:`rig.place_and_route.place_and_route_wrapper`
* :py:mod:`rig.machine_control.MachineController`

Tutorial:

* :py:ref:`tutorial-05`


Place and route for external devices
====================================

.. doctest::
    
    >>> # Assuming a graph defined as in the place-and-route example, lets add
    >>> # a new vertex representing a device (e.g. as a silicon retina) directly
    >>> # attached to the 'West' link of chip (0, 0), e.g. via a 2-of-7 or
    >>> # S-ATA link.
    
    >>> from rig.place_and_route import place_and_route_wrapper
    >>> from rig.place_and_route.constraints import \
    ...     LocationConstraint, RouteEndpointConstraint
    >>> from rig.routing_table import Routes
    >>> from rig.netlist import Net
    
    >>> # Make a vertex to represent the device which consumes no Cores or
    >>> # SDRAM.
    >>> device_vertex = object()
    >>> vertices_resources[device_vertex] = {}
    
    >>> # Use a pair of constraints to indicate that the vertex is attached
    >>> # to the West link of (0, 0).
    >>> constraints = [
    ...     LocationConstraint(device_vertex, (0, 0)),
    ...     RouteEndpointConstraint(device_vertex, Routes.west),
    ... ]
    
    >>> # Any Net sourced or sunk by our device_vertex will be routed down the
    >>> # appropriate link.
    
    >>> # The constraint list must be passed in during place and route. 
    >>> placements, allocations, application_map, routing_tables = \
    ...     place_and_route_wrapper(vertices_resources, vertices_applications,
    ...                             nets, net_keys, system_info, constraints)

Reference:

* :py:mod:`rig.place_and_route`
* :py:mod:`rig.place_and_route.constraints`
