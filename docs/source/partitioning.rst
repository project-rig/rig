Partitioning problem graphs
###########################

It is usual for problems mapped to SpiNNaker to consist of objects which are
made of irreducible chunks ("atoms") of computational work and memory usage.
Partitioning determines how many atoms may be grouped together to allow
computation to fit within the time/memory constraints of a single core.
Of course, it is possible to partition on any suitable constraint.

We believe that partitioning is a problem-specific issue, but we provide a way
of expressing constraints that we believe is useful and a simple partitioner
that will work as long as constraints are not conflicting (e.g., to reduce
memory usage CPU time is increased).

Expressing constraints
----------------------

Constraints represent the usage of a particular resource.  Our partitioner
expects them to report how many cuts must be made to an object to fit each
slice within the constraints of the resource.  Constraints are callables that
when called return an integer number of cuts.  An easy way to build a new
constraint is to subclass :py:class:`~rig.partitioner.Constraint` and override
the :py:func:`get_usage` method::

        # Create a constraint that will ensure vertices are split such that the
        # number of widgets used fits within bounds.
        class WidgetConstraint(rig.partitioner.Constraint):
            def get_usage(self, vertex, vertex_slice):
                """This method should accept a vertex and a Python slice object
                indicating which atoms are being queried and get the resource usage
                for those atoms of the vertex.  In this example we can just call
                `vertex.get_n_widgets` with the slice.
                """
                return vertex.get_n_widgets(vertex_slice)

Partitioning vertices
---------------------

Our sample partitioner accepts a single object, a list of constraint objects
which can retrieve resource utilisation from that object and returns a list of
slices of the vertex that meet all the constraints::

    # Create some constraints to use to partition a vertex
    widget_constraint = WidgetConstraint(max=5)  # Max of 5 widgets per cut
    sdram_constraint = SDRAMConstraint(max=8*1024*1024, target=0.9)  # Aim for 90% SDRAM usage
    cpu_constraint = CPUConstraint(max=200000, target=0.8)  # Aim for 80% DTCM usage
    dtcm_constraint = DTCMConstraint(max=64*1024, target=0.9)  # Aim for 90% CPU Usage

    # Apply the partitioner to a vertex
    slices = rig.partitioner.partition(vertex, constraints=[widget_constraint, sdram_constraint,
                                                            cpu_constraint, dtcm_constraint])
