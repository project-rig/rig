"""Wraps the "rig_c_sa" Python C extension library in a Kernel object."""

from collections import defaultdict

from six import iteritems

import pkg_resources

# An optional Rig dependency.
from rig_c_sa import ffi
import rig_c_sa


# Make sure installed rig_c_sa version is compatible.
pkg_resources.require("rig_c_sa>=0.3.1,<1.0.0")


class CKernel(object):
    """An implementation of the Simulated Annealing placement algorithm kernel
    written in C.

    Thanks to being written in C, this kernel is 50-150x faster than
    :py:class:`~rig.place_and_route.place.sa.python_kernel.PythonKernel` while
    maintaining the same placement quality. Since installing the C
    kernel requires a compiler it is not included in the standard Rig package.
    The C kernel can be installed using::

        $ pip install rig_c_sa

    The `rig_c_sa <https://github.com/project-rig/rig_c_sa>`_ package is a
    Python/C library containing the C components of the algorithm. Installation
    requires that you have C compiler installed along with `libffi
    <https://sourceware.org/libffi/>`_.
    """

    def __init__(self, vertices_resources, movable_vertices, fixed_vertices,
                 initial_placements, nets, machine, random, **kwargs):

        # Seed the random number generator
        rig_c_sa.srand(random.getrandbits(32))

        # Allocate the basic state for the kernel
        self.s = rig_c_sa.sa_new(machine.width, machine.height,
                                 len(machine.chip_resources),
                                 len(vertices_resources),
                                 len(nets))
        assert self.s != ffi.NULL

        # Automatically free SA state on GC of pointer to it
        self.s = ffi.gc(self.s, rig_c_sa.sa_free)

        # Set basic kernel attributes
        self.s.has_wrap_around_links = machine.has_wrap_around_links()
        self.s.num_movable_vertices = len(movable_vertices)

        # Get lookup from vertices to set of nets, suppressing duplicates.
        vertices_nets = defaultdict(set)
        for net in nets:
            for vertex in net:
                vertices_nets[vertex].add(net)

        # Create all vertices and set assign initial positions. Populates a map
        # from Python vertex object to C sa_vertex_t pointer.
        self.vertices_c = {}
        for i, vertex in enumerate(vertices_resources):
            # Create the vertex
            v = rig_c_sa.sa_new_vertex(self.s, len(vertices_nets[vertex]))
            assert v != ffi.NULL
            self.s.vertices[i] = v

            # Add to lookup
            self.vertices_c[vertex] = v

            # Set resource consumption
            for i, resource in enumerate(machine.chip_resources):
                v.vertex_resources[i] = \
                    vertices_resources[vertex].get(resource, 0)

            # Add to chip selected by initial placement
            x, y = initial_placements[vertex]
            rig_c_sa.sa_add_vertex_to_chip(self.s, v, x, y,
                                           vertex in movable_vertices)

        # Create all nets
        for i, net in enumerate(nets):
            # Remove duplicate vertices from the net (e.g. for self-loops only
            # include the source/sink vertex once).
            vertices = set(net)

            # Create the net
            n = rig_c_sa.sa_new_net(self.s, len(vertices))
            assert n != ffi.NULL
            self.s.nets[i] = n
            n.weight = net.weight

            # Add vertices to it
            for vertex in vertices:
                rig_c_sa.sa_add_vertex_to_net(self.s, n,
                                              self.vertices_c[vertex])

        # Set chip resource availability (note we override the changes made by
        # inserting the vertices above)
        for x, y in machine:
            for i, resource in enumerate(machine.chip_resources):
                rig_c_sa.sa_set_chip_resources(self.s, x, y, i,
                                               machine[(x, y)][resource])

    def run_steps(self, num_steps, distance_limit, temperature):
        # Allocate memory for values returned via arguments
        num_accepted = ffi.new("size_t *")
        cost_delta = ffi.new("double *")
        cost_delta_sd = ffi.new("double *")

        # Run the step as requested
        rig_c_sa.sa_run_steps(self.s, num_steps, distance_limit, temperature,
                              num_accepted, cost_delta, cost_delta_sd)

        # Calculate new cost
        cost = rig_c_sa.sa_get_total_cost(self.s)

        return num_accepted[0], cost, cost_delta_sd[0]

    def get_placements(self):
        return {vertex: (v.x, v.y) for vertex, v in iteritems(self.vertices_c)}
