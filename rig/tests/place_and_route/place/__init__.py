"""A selection of placement algorithms.

This module should contain a selection of placement algorithms, each located in
their own submodule and be named `place`. See the documentation for the parent
(`par`) module for the standard interface exposed by all placers.

Note to placer developers
-------------------------
* A modest suite of generic placement tests can be found in
  `tests/par/place/test_generic.py`. You should add your placer to the list of
  placers to be tested at the top of this file to reap the benefits of these
  basic "sanity check" tests.
* A number of utility functions which may be useful within a placer
  implementation can be found in
  :py:class:`~.rig.place_and_route.place.common`.
"""
