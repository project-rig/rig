Building up a keyspace for multicast packets
============================================

.. autoclass:: rig.keyspaces.Keyspace

Adding fields to a keyspace
---------------------------

.. automethod:: rig.keyspaces.Keyspace.add_field

Adding values to fields to create new keyspaces
-----------------------------------------------

.. automethod:: rig.keyspaces.Keyspace.__call__

Fixing field sizes and layout
-----------------------------

.. automethod:: rig.keyspaces.Keyspace.assign_fields


Getting keys and masks
----------------------

.. automethod:: rig.keyspaces.Keyspace.get_key
.. automethod:: rig.keyspaces.Keyspace.get_mask
