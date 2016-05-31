Rig - libraries for SpiNNaker application support
=================================================

.. image:: logo.png

Rig is a Python library which contains a collection of complementary tools for
developing applications for the massively-parallel SpiNNaker_ architecture.
First and foremost, Rig aims to present a light-weight, well tested and well
documented interface for SpiNNaker application developers.

.. _SpiNNaker: http://apt.cs.manchester.ac.uk/projects/SpiNNaker/

Getting started
---------------

If you're new to Rig, here are two options for getting started: If you're
feeling impatient and want to start playing, take a look at :ref:`some of the
ten-line quick-start example programs <ten-lines>`. Alternatively the
:ref:`'hello world' to circuit simulator tutorial<circuit-sim-tutorial>` gives
a detailed introduction to building real-world SpiNNaker applications using Rig
(still in under 400 lines of heavily commented Python).

.. toctree::
    :maxdepth: 2
    
    install

.. toctree::
    :maxdepth: 2
    
    circuit_sim_tutorial/index.rst

.. toctree::
    :maxdepth: 2

    control_tutorials

.. toctree::
    :maxdepth: 1
    
    bitfield_tutorial_doctest

.. toctree::
    :maxdepth: 2
    
    ten_lines/index.rst

Reference manual
----------------

The Rig reference manual describes Rig's public APIs, grouped by function. Most
of this documentation is also accessible using Python's :py:func:`help`
facility.

Data packaging for SpiNNaker
````````````````````````````

.. toctree::
    :maxdepth: 2
    
    type_casts
    bitfield_doctest

Graph-to-machine mapping
````````````````````````

.. toctree::
    :maxdepth: 3
    
    place_and_route
    routing_table_tools_doctest
    geometry


Execution control and machine management
````````````````````````````````````````

.. toctree::
    :maxdepth: 2
    
    control
    wizard


Standalone utility applications
```````````````````````````````

.. toctree::
    :maxdepth: 2
    
    utility_apps

Indicies and Tables
-------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

