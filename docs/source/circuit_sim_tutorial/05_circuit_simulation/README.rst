.. _tutorial-05:

05: Circuit Simulation
======================

In the :ref:`previous part of this tutorial <tutorial-04>` we built a simple
digital circuit simulator using several application kernels running on
multiple SpiNNaker chips which communicated with multicast packets. In our
proof-of-concept host program, the chip and core to use for each kernel was
chosen by hand and all routing tables were written manually. Though this works,
it made our simulator incredibly inflexible and the host program hard to modify
and extend.

In this part of the tutorial we'll leave the application kernels unchanged but
re-write our host program to make use of the automatic place-and-route tools
provided by Rig. These tools automate the process of assigning application
kernels to specific cores and generating routing tables while attempting to
make efficient use of the machine. We'll also restructure our host program to
be more like a real-world application complete with a simple user-facing
interface.

The source files used in this tutorial can be downloaded below:

* Host program
    * :download:`circuit_simulator.py`
* Example circuit simulation script
    * :download:`example_circuit.py`
* SpiNNaker kernels (unchanged from :ref:`part 04 <tutorial-04>`)
    * :download:`gate.c`
    * :download:`stimulus.c`
    * :download:`probe.c`
    * :download:`Makefile`

Defining the circuit simulator user interface/API
-------------------------------------------------

If our circuit simulator is to be useful it must present a sensible API to
allow users to describe their circuits. In this example we'll implement an API
which looks like this:

.. literalinclude:: example_circuit.py
    :language: python
    :lines: 7-46

This script defines the same circuit which we hard-coded in :ref:`part 04
<tutorial-04>`\ :

.. figure:: ../04_circuit_simulation_proof_of_concept/diagrams/example_circuit.png
    :alt: A simple circuit with three stimuluses, an OR and AND gate and probe.

With our desired API in mind, lets design our circuit simulator!

Place and Route using Rig
-------------------------

Before diving into the code it is first important to understand what the Rig
place-and-route tools do.

Rig provides a suite of placement and routing algorithms in its
:py:mod:`rig.place_and_route` module. In essence, these algorithms accept
abstract descriptions of graphs of communicating SpiNNaker application kernels
as input. Based on this information the place and route algorithms select which
core each kernel will be loaded onto, keeping communicating cores close
together to reduce network load. In addition, routing tables which make
efficient use of SpiNNaker's network are generated.

In Rig terminology, the abstract (hyper-)graph of application kernels are known
as *vertices* which are connected together by *nets*:

vertices
    Approximately speaking, a vertex represents a group of cores and SDRAM
    which must be assigned in one piece to a chip somewhere. In our circuit
    simulator, a vertex represents a single gate, stimulus or probe and each
    requires a single core and some quantity of SDRAM.

nets
    A net typically represents a 1-to-many flow of multicast packets between
    vertices. A net has a single *source* vertex and many *sink* vertices. In
    our circuit simulator, a net corresponds to a wire in our circuit, where the
    source is the gate or stimulus output driving the wire and the sinks are
    the connected gate and probe inputs.

In addition to graph of vertices and nets, the place and route tools require a
description of the SpiNNaker machine our simulation will be running on. As we
will see later, the :py:class:`~rig.machine_control.MachineController` provides
a method for gathering this information.


Building the circuit simulator API
----------------------------------

What follows is a (non-linear) walk-through of the most important parts of the
circuit simulator host program provided in ``circuit_simulator.py``.

In most host applications built with Rig, the graph of vertices and nets fed to
the place and route tools are generated from application-specific data
structures shortly before performing the place-and-route. This allows the
majority of the application to use data structures which best fit the
application. In this circuit simulator example we'll follow this approach too,
so let's start by defining the Python classes which make up the API.

Defining a wire
```````````````

A wire represents a connection from one the output of one component to the
inputs of many other components and is defined as follows:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 21-41

A ``_Wire`` instance contains a source component, a :py:class:`list` of sink
components and a unique routing key to use in the simulation. The ``Simulator``
object (to be defined later) will be responsible for creating new ``_Wire``
objects.

Defining components (gates, stimuli and probes)
```````````````````````````````````````````````

At the heart of our circuit simulator is our two-input, one-output,
lookup-table-based logic gate so let's define our ``Gate`` component first like
so:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 44-83

In the constructor we simply store a reference to the ``Simulator`` object
along with a copy of the lookup table provided. We also inform the
``Simulator`` of the existance of the component using
``Simulator._add_component``. The ``_inputs`` attribute will hold references to
the ``_Wires`` connected to each input and the ``output`` attribute holds a
reference to (a newly created) ``_Wire`` which will be driven by the gate.

The ``Gate.connect_input`` method connects a ``_Wire`` to an input by storing a
reference to the ``_Wire`` object and adding the component to the ``_Wire``\ 's
list of sinks.

We also define various subclasses of ``Gate`` which, for the sake of
convenience, simply define the lookup table to be used. For example an AND-gate
component is defined like so:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 118-122

The ``Probe`` object is defined in a similar way to the ``Gate`` but doesn't
define an output:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 152-175

Finally, the ``Stimulus`` object is defined but, since it doesn't have any
inputs, the ``connect_input`` method is excluded:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 213-235

Defining the simulator
``````````````````````

All that remains to be defined of our API is the ``Simulator`` object. The
``Simulator`` simply stores the hostname and simulation length provided and
maintains lists of components and wires which have been added to the
simulation:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 266-301


Making it work
--------------

At this point, our API is complete with the notable exception of the
``Simulation.run()`` method.  At a high level, the ``run()`` method performs
the following steps:

* Build a graph of the form accepted by Rig's place and route tools.
* Perform place and route.
* Load the configuration data, routing tables and application kernels required.
* Run the simulation.
* Read back results captured by probes.

We'll now proceed to break down this function and look at its operation in
detail.

Building a place-and-routeable graph
````````````````````````````````````

To perform place and route we must build a graph describing our simulation in
the format required by Rig.

The first thing we need to do is define the resources required by each vertex
in the graph. Rig allows us to use any Python :py:class:`object` to represent a
vertex and since each component in our simulation will become a vertex in our
graph we'll use the :py:class:`object`\ s we defined above to identify the
vertices. We build a ``vertices_resources`` dictionary which enumerates the
resources consumed by each vertex in our application:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 306-311
    :dedent: 8

Each entry in the ``vertices_resources`` dictionary contains another dictionary
mapping 'resources' to the required quantities of each resource. As in most
applications, the only resources we care about are Cores and SDRAM. By
convention these resources are identified to by the corresponding
:py:data:`~rig.place_and_route.Cores` and :py:data:`~rig.place_and_route.SDRAM`
`sentinels <https://pypi.python.org/pypi/sentinel>`_ defined by Rig.

Each vertex requires exactly one core but the amount of SDRAM required depends
on the type of component and length of the simulation. A ``_get_config_size()``
method is added to each of our component types to compute their SDRAM
requirements:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 44,89-92

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 152,181-185

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 213,241-245

Next we must also define the filename of the spinnaker application kernel (i.e.
the APLX file) used for each vertex.

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 315-316
    :dedent: 8

Once again we support this by adding a ``_get_kernel()`` method to each
component type:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 44,85-87

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 152,177-179

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 213,237-239

Next, we enumerate the nets representing the streams of multicast packets
flowing between vertices, as well as the routing keys and masks used for each
net. Rig expects nets to be defined by :py:class:`~rig.netlist.Net` objects.
Like the ``_Wire`` objects in our simulator, :py:class:`~rig.netlist.Net`\ s
simply contain a source vertex and a list of sink vertices. In the code below
we build a :py:class:`dict` mapping :py:class:`~rig.netlist.Net`\ s to ``(key,
mask)`` tuples for each wire in the simulation:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 320-323
    :dedent: 8

The final piece of information required is a description of the SpiNNaker
machine onto which our application will be placed and routed. Using a
:py:class:`~rig.machine_control.MachineController` we first
:py:meth:`~rig.machine_control.MachineController.boot` the machine and then
interrogate it using
:py:meth:`~rig.machine_control.MachineController.get_system_info` which returns
a :py:class:`~rig.machine_control.machine_control.SystemInfo` object. This
object contains a detailed description of the machine, for example, enumerating
working cores and links. This description will be used shortly to perform place
and route.

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 327-329
    :dedent: 8

Place and route
```````````````

The place and route process can be broken up into many steps such as placement,
allocation, routing and routing table generation. Though some advanced
applications may find it useful to break these steps apart, our circuit
simulator, like many other applications, does not. Rig provides a
:py:func:`~rig.place_and_route.place_and_route_wrapper` function which saves us
from the 'boilerplate' of doing each step separately. This function takes the
graph description we constructed above and performs the place and route process
in its entirety.

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 333-337
    :dedent: 8

The ``placements`` and ``allocations`` :py:class:`dict` returned by
:py:func:`~rig.place_and_route.place_and_route_wrapper` together define the
specific chip and core each vertex has been assigned to (see
:py:func:`~rig.place_and_route.place` and
:py:func:`~rig.place_and_route.allocate` for details).

``application_map`` is a  :py:class:`dict` describing what application kernels
need to be loaded onto what cores in the machine.

Finally, ``routing_tables`` contains a :py:class:`dict` giving the routing
tables to be loaded onto each core in the machine.

Loading and running the simulation
``````````````````````````````````

We are now ready to load and execute our circuit simulation on SpiNNaker. The
first step is to allocate blocks of SDRAM containing configuration data on
every chip where our application kernels will run.

The :py:func:`~rig.machine_control.utils.sdram_alloc_for_vertices` utility
function takes a :py:class:`~rig.machine_control.MachineController` and the
``placements`` and ``allocations`` :py:class:`dict`\ s produced during place
and route and allocates a block of SDRAM for each vertex. Each allocation is
given a tag matching the core number of the vertex, and the size of the
allocation is determined by the quantity of
:py:data:`~rig.place_and_route.SDRAM` consumed by the vertex, as originally
indicated in ``vertices_resources``.

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 341-342
    :dedent: 12

The :py:class:`dict` returned is a mapping from each vertex (i.e. instances of
our component classes) to a
:py:class:`~rig.machine_control.machine_controller.MemoryIO` file-like
interface to SpiNNaker's memory.

We add a ``_write_config`` method to each of our component classes which is
passed a :py:class:`~rig.machine_control.machine_controller.MemoryIO` object
into which configuration data is written.

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 345-346
    :dedent: 12

The ``_write_config`` functions for each component type are as follows:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 44,94-111

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 152,187-196

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 213,247-259

Next, the routing tables and SpiNNaker applications are loaded using
:py:meth:`~rig.machine_control.MachineController.load_routing_tables` and
:py:meth:`~rig.machine_control.MachineController.load_application`:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 348-352
    :dedent: 12

We now wait for the applications to reach their initial barrier, send the
'sync0' signal to start simulation and, finally, wait for the cores to exit.

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 354-361
    :dedent: 12

The last step is to read back results from the machine. As with loading, we add
a ``_read_results`` method to each component type which we call with a
:py:class:`~rig.machine_control.machine_controller.MemoryIO` object from which
it should read any results it requires:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 364-365
    :dedent: 12

The ``_read_results`` method is a no-op for all but the ``Probe`` component
whose implementation is as follows:

.. literalinclude:: circuit_simulator.py
    :language: python
    :lines: 152,198-210

Trying it out
-------------

Congratulations! Our circuit simulator is now complete! We can now run the
example script we used to define our simulator's API and within a second or so
we have our results!

::

    $ python example_circuit.py HOSTNAME_OR_IP
    Stimulus A: 0000000011111111000000001111111100000000111111110000000011111111
    Stimulus B: 0000000000000000111111111111111100000000000000001111111111111111
    Stimulus C: 0000000000000000000000000000000011111111111111111111111111111111
    Probe:      0000000000000000000000000000000001000000001111111111111111111111

