# Rig

[![Build Status](https://travis-ci.org/project-rig/rig.svg?branch=master)](https://travis-ci.org/project-rig/rig)
[![PyPi version](https://pypip.in/v/rig/badge.png)](https://pypi.python.org/pypi/rig/)
[![Documentation Status](https://readthedocs.org/projects/rig/badge/?version=master)](https://readthedocs.org/projects/rig/?badge=master)

Rig is a set of Python and C libraries for mapping computational problems to
SpiNNaker and interacting with them.  Above all it aims to be light weight and
to present common and well-documented interfaces to all of its parts.

Rig is split into three primary groups of tools and utilities:

## Execution specification

Allows specification of the sets of executables that are to be simulated on
SpiNNaker.  Tools exist for:

 - Specifying regions of memory.
 - Generating "keyspaces" for routing multicast packets.
 - Converting from Numpy arrays and floats to fix-point values and vice-versa.
 - Specifying a problem for SpiNNaker in terms of computational nodes and their
   communication.

## Problem mapping

 - Placing: Taking a set of computational nodes and determining which SpiNNaker
   processing cores they should be placed on.
 - Routing: Taking a set of computational nodes and determining the routing
   entries necessary to fulfil their communication needs.

## Execution control

 - A light-weight SCP interface to load applications and data onto a SpiNNaker
   machine and to control their execution.

## Related projects

 - Clock discipline
 - Routing table minimisation
 - Optimal routing key allocation

# Documentation

The Rig documentation is hosted at: http://rig.readthedocs.org/
