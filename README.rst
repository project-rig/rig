Rig
===

.. image:: ./docs/source/logo.png?raw=True
   :alt: The Rig Logo

.. image:: https://img.shields.io/pypi/v/rig.svg?style=flat
   :alt: PyPi version
   :target: https://pypi.python.org/pypi/rig/
.. image:: https://readthedocs.org/projects/rig/badge/?version=stable
   :alt: Documentation
   :target: http://rig.readthedocs.org/
.. image:: https://travis-ci.org/project-rig/rig.svg?branch=master
   :alt: Build Status
   :target: https://travis-ci.org/project-rig/rig
.. image:: https://img.shields.io/codecov/c/github/project-rig/rig/master.svg
   :alt: Coverage Status
   :target: https://codecov.io/github/project-rig/rig

Rig is a Python library which contains a collection of complementary tools for
developing applications for the massively-parallel
`SpiNNaker <http://apt.cs.manchester.ac.uk/projects/SpiNNaker/>`_ architecture.
First and foremost, Rig aims to present a light-weight, well tested and well
documented interface for SpiNNaker application developers.

Quick-start
-----------

The latest stable release can be installed from the `Python Package
Index <https://pypi.python.org/pypi/rig/>`_ using::

    pip install rig

The corresponding `documentation is available on
ReadTheDocs <http://rig.readthedocs.org/>`_.

See `DEVELOP.md`__ for information on how to get involved in Rig development
or install the latest development version.

__ ./DEVELOP.md

Overview
--------

Rig does not mandate any particular application work flow but rather provides a
set of common utilities with well-defined, composable interfaces. Developers
are encouraged to use whatever subset of these tools they consider useful.

The utilities provided by Rig can be broken down approximately as follows:

* Data packaging for SpiNNaker

  * ``type_casts``: conversion functions between common
    Python and Numpy data types and the fixed-point types used by SpiNNaker.
  * ``bitfield.BitField``: an abstraction for flexibly defining routing keys
    for SpiNNaker applications ranging from the trivial to those involving
    multiple external devices with conflicting routing key formats.

* Graph-to-machine mapping

  * ``place_and_route``: a suite of algorithms for mapping graph-like problems
    onto the SpiNNaker hardware, allocating on-chip resources and generating
    routing tables.
  * ``routing_table``: a suite of algorithms for minimising and analysing
    SpiNNaker's multicast routing tables.
  * ``geometry``: utility functions for working with SpiNNaker's hexagonal
    torus topology.

* Execution control and machine management

  * ``machine_control.MachineController``: a high-level interface to SpiNNaker
    machines. Can be used to boot machines, load and control applications,
    and more.
  * ``machine_control.BMPController``: a high-level interface to the
    Board Management Processors (BMPs) found in large SpiNNaker
    installations. Can be used to control system power and read diagnostic
    information such as temperature and FPGA status.

* Standalone utility applications

  * ``rig-boot``: No-nonsense command line utility for booting SpiNNaker
    systems.
  * ``rig-power``: No-nonsense command line utility for power-cycling SpiNNaker
    systems.
  * ``rig-info``: No-nonsense command line utility to get high-level
    information about a SpiNNaker system, e.g. "what is it running, is it on
    fire?".
  * ``rig-discover``: No-nonsense command line utility for discovering the IP of
    connected, unbooted SpiNNaker boards.
  * ``rig-iobuf``: No-nonsense command line utility for reading IOBUF messages
    from a SpiNNaker application.
  * ``rig-ps``: No-nonsense command line utility for listing all applications
    (and their locations) in a SpiNNaker machine.
  * ``rig-counters``: No-nonsense command line utility which can
    non-intrusively monitor a SpiNNaker system for dropped packets.

Python Version Support
----------------------

Rig is tested against the following versions of Python:

* 2.7
* 3.4
* 3.5

Other versions may or may not work.

Contributors
------------

See `CONTRIBUTORS.md`__ for a list of all the folk who've
contributed to Rig.

__ ./CONTRIBUTORS.md


License
-------

Rig is licensed under the `GNU General Public License Version 2`_.

.. _GNU General Public License Version 2: ./LICENSE
