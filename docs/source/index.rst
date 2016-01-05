Rig - libraries for SpiNNaker application support
=================================================

.. image:: logo.png

Rig is a Python library which contains a collection of complementary tools for
developing applications for the massively-parallel SpiNNaker_ architecture.
First and foremost, Rig aims to present a light-weight, well tested and well
documented interface for SpiNNaker application developers.

.. _SpiNNaker: http://apt.cs.manchester.ac.uk/projects/SpiNNaker/

The following documentation aims to provide new users with a high-level
introduction to all of the key parts of Rig and also present a formal API
reference which is also available via Python's ``help()`` system.

Data packaging for SpiNNaker
----------------------------

.. toctree::
        :maxdepth: 2

        type_casts
        bitfield_doctest

Graph-to-machine mapping
------------------------

.. toctree::
        :maxdepth: 3
        
        place_and_route
        routing_table_tools_doctest
        geometry


Execution control and machine management
----------------------------------------

.. toctree::
        :maxdepth: 2

        control
        wizard


Standalone utility applications
-------------------------------

.. toctree::
        :maxdepth: 2

        utility_apps

Indicies and Tables
-------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

