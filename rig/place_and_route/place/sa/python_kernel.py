"""A Python implementation of the Simulated Annealing kernel."""

from six import iteritems

import math

import time

import importlib

from rig.place_and_route.place.utils import \
    add_resources, subtract_resources, overallocated

import warnings


class PythonKernel(object):
    """An implementation of the Simulated Annealing placement algorithm kernel
    written in Python.

    This implementation is not optimised for runtime but should produce good
    quality, correct results on any platform, albeit slowly.

    This kernel will display a warning/hint if placement is taking a long time
    suggesting installing ``rig_c_sa`` to enable use of the faster
    :py:class:`~rig.place_and_route.place.place.sa.c_kernel.CKernel`. To
    disable this warning, the kernel takes an optional ``no_warn`` argument
    which, when True, disables the warning.
    """

    """Display a warning/hint to install rig_c_sa if placement takes longer
    than this many seconds.
    """
    WARN_TIME = 2.0 * 60.0

    def __init__(self, vertices_resources, movable_vertices, fixed_vertices,
                 initial_placements, nets, machine, random, no_warn=False):
        self.vertices_resources = vertices_resources
        self.movable_vertices = list(v for v in vertices_resources
                                     if v in movable_vertices)
        self.fixed_vertices = fixed_vertices
        self.placements = initial_placements.copy()
        self.nets = nets
        self.machine = machine
        self.random = random

        if no_warn:
            self.start_time = None
        else:
            self.start_time = time.time()

        self.has_wrap_around_links = self.machine.has_wrap_around_links()

        # Location-to-Vertices: A lookup {(x, y): [vertex, ...], ...} giving
        # the set of vertices on a given chip.  Chips which are not in the
        # machine are excluded from this lookup.
        self.l2v = {xy: [] for xy in self.machine}
        for vertex, location in iteritems(self.placements):
            self.l2v[location].append(vertex)

        # Vertices-to-Nets: A lookup {vertex: [Net, ...], ...}, gives a list of
        # nets of which the given vertex is a member.
        self.v2n = {v: [] for v in self.vertices_resources}
        for net in nets:
            for v in net:
                if net not in self.v2n[v]:
                    self.v2n[v].append(net)

    def run_steps(self, num_steps, distance_limit, temperature):
        # If the placement runs for a long time, hint that the C-based placer
        # is much faster.
        if (self.start_time is not None and
                time.time() - self.start_time > self.WARN_TIME):
            # Only show the warning/hint if the C Kernel is not installed.
            try:
                # NB: This import is performed using import lib rather than an
                # import statement to enable easier testing since this function
                # call can be trivially mocked out.
                importlib.import_module(
                    "rig.place_and_route.place.sa.c_kernel")
            except ImportError:
                warnings.warn(
                    "It appears you are placing a large graph using the "
                    "slow Python-based simulated annealing kernel. "
                    "Installing the rig_c_sa package may result in a 50-150x "
                    "speedup without any change to your code.",
                    stacklevel=3)

            # Prevent future warnings
            self.start_time = None

        num_accepted = 0
        deltas = []
        for _ in range(num_steps):
            swapped, delta = _step(self.movable_vertices,
                                   distance_limit, temperature,
                                   self.placements, self.l2v, self.v2n,
                                   self.vertices_resources,
                                   self.fixed_vertices,
                                   self.machine,
                                   self.has_wrap_around_links,
                                   self.random)
            num_accepted += 1 if swapped else 0
            deltas.append(delta)
        mean = sum(deltas) / float(len(deltas))
        std = math.sqrt(sum((v-mean)**2 for v in deltas) / len(deltas))

        cost = sum((_net_cost(net, self.placements, self.has_wrap_around_links,
                              self.machine)
                    for net in self.nets), 0.0)

        return num_accepted, cost, std

    def get_placements(self):
        return self.placements


def _net_cost(net, placements, has_wrap_around_links, machine):
    """Get the cost of a given net.

    This function, in principle at least, should estimate the total network
    resources consumed by the given net. In practice this estimate is based on
    the size of the bounding-box of the net (i.e. HPWL). This should be
    improved at some later time to better account for the effects of large
    fan-outs.

    Parameters
    ----------
    net : :py:class:`rig.netlist.Net`
    placements : {vertex: (x, y), ...}
    has_wrap_around_links : bool
    machine : :py:class:`rig.place_and_route.Machine`

    Returns
    -------
    float
    """
    # This function is by far the hottest code in the entire algorithm, as a
    # result, small performance improvements in here can have significant
    # impact on the runtime of the overall algorithm. As an unfortunate side
    # effect, this code is rather ugly since many higher-level constructs (e.g.
    # min/max) are outrageously slow.

    # XXX: This does not account for the hexagonal properties of the SpiNNaker
    # topology.
    if has_wrap_around_links:
        # When wrap-around links exist, we find the minimal bounding box and
        # return the HPWL weighted by the net weight. To do this the largest
        # gap between any pair of vertices is found::
        #
        #     |    x     x             x   |
        #                ^-------------^
        #                    max gap
        #
        # The minimal bounding box then goes the other way around::
        #
        #     |    x     x             x   |
        #      ----------^             ^---

        # First we collect the x and y coordinates of all vertices in the net
        # into a pair of (sorted) lists, xs and ys.
        x, y = placements[net.source]
        num_vertices = len(net.sinks) + 1
        xs = [x] * num_vertices
        ys = [y] * num_vertices
        i = 1
        for v in net.sinks:
            x, y = placements[v]
            xs[i] = x
            ys[i] = y
            i += 1

        xs.sort()
        ys.sort()

        # The minimal bounding box is then found as above.
        x_max_delta = 0
        last_x = xs[-1] - machine.width
        for x in xs:
            delta = x - last_x
            last_x = x
            if delta > x_max_delta:
                x_max_delta = delta

        y_max_delta = 0
        last_y = ys[-1] - machine.height
        for y in ys:
            delta = y - last_y
            last_y = y
            if delta > y_max_delta:
                y_max_delta = delta

        return (((machine.width - x_max_delta) +
                 (machine.height - y_max_delta)) *
                net.weight *
                math.sqrt(len(net.sinks) + 1))
    else:
        # When no wrap-around links, find the bounding box around the vertices
        # in the net and return the HPWL weighted by the net weight.
        x1, y1 = x2, y2 = placements[net.source]
        for vertex in net.sinks:
            x, y = placements[vertex]
            x1 = x if x < x1 else x1
            y1 = y if y < y1 else y1
            x2 = x if x > x2 else x2
            y2 = y if y > y2 else y2

        return (((x2 - x1) + (y2 - y1)) *
                float(net.weight) *
                math.sqrt(len(net.sinks) + 1))


def _vertex_net_cost(vertex, v2n, placements, has_wrap_around_links, machine):
    """Get the total cost of the nets connected to the given vertex.

    Parameters
    ----------
    vertex
        The vertex whose nets we're interested in.
    v2n : {vertex: [:py:class:`rig.netlist.Net`, ...], ...}
    placements : {vertex: (x, y), ...}
    has_wrap_around_links : bool
    machine : :py:class:`rig.place_and_route.Machine`

    Returns
    -------
    float
    """
    total_cost = 0.0
    for net in v2n[vertex]:
        total_cost += _net_cost(net, placements, has_wrap_around_links,
                                machine)

    return total_cost


def _get_candidate_swap(resources, location,
                        l2v, vertices_resources, fixed_vertices, machine):
    """Given a chip location, select a set of vertices which would have to be
    moved elsewhere to accommodate the arrival of the specified set of
    resources.

    Parameters
    ----------
    resources : {resource: value, ...}
        The amount of resources which are required at the specified location.
    location : (x, y)
        The coordinates of the chip where the resources are sought.
    l2v : {(x, y): [vertex, ...], ...}
    vertices_resources : {vertex: {resource: value, ...}, ...}
    fixed_vertices : {vertex, ...}
    machine : :py:class:`rig.place_and_route.Machine`

    Returns
    -------
    [Vertex, ...] or None
        If a (possibly empty) list, gives the set of vertices which should be
        removed from the specified location to make room.

        If None, the situation is impossible.
    """
    # The resources already available at the given location
    chip_resources = machine[location]

    # The set of vertices at that location
    vertices = l2v[location]

    # The set of vertices to be moved from the location to free up the
    # specified amount of resources
    to_move = []

    # While there's not enough free resource, remove an arbitrary (movable)
    # vertex from the chip.
    i = 0
    while overallocated(subtract_resources(chip_resources, resources)):
        if i >= len(vertices):
            # Run out of vertices to remove from this chip, thus the situation
            # must be impossible.
            return None
        elif vertices[i] in fixed_vertices:
            # Can't move fixed vertices, just skip them.
            i += 1
            continue
        else:
            # Work out the cost change when we remove the specified vertex
            vertex = vertices[i]
            chip_resources = add_resources(chip_resources,
                                           vertices_resources[vertex])
            to_move.append(vertex)
            i += 1

    return to_move


def _swap(vas, vas_location, vbs, vbs_location, l2v, vertices_resources,
          placements, machine):
    """Swap the positions of two sets of vertices.

    Parameters
    ----------
    vas : [vertex, ...]
        A set of vertices currently at vas_location.
    vas_location : (x, y)
    vbs : [vertex, ...]
        A set of vertices currently at vbs_location.
    vbs_location : (x, y)
    l2v : {(x, y): [vertex, ...], ...}
    vertices_resources : {vertex: {resource: value, ...}, ...}
    placements : {vertex: (x, y), ...}
    machine : :py:class:`rig.place_and_route.Machine`
    """
    # Get the lists of vertices at either location
    vas_location2v = l2v[vas_location]
    vbs_location2v = l2v[vbs_location]

    # Get the resource availability at either location
    vas_resources = machine[vas_location]
    vbs_resources = machine[vbs_location]

    # Move all the vertices in vas into vbs.
    for va in vas:
        # Update the placements
        placements[va] = vbs_location

        # Update the location-to-vertex lookup
        vas_location2v.remove(va)
        vbs_location2v.append(va)

        # Update the resource consumption after the move
        resources = vertices_resources[va]
        vas_resources = add_resources(vas_resources, resources)
        vbs_resources = subtract_resources(vbs_resources, resources)

    for vb in vbs:
        # Update the placements
        placements[vb] = vas_location

        # Update the location-to-vertex lookup
        vbs_location2v.remove(vb)
        vas_location2v.append(vb)

        # Update the resource consumption after the move
        resources = vertices_resources[vb]
        vas_resources = subtract_resources(vas_resources, resources)
        vbs_resources = add_resources(vbs_resources, resources)

    # Update the resources in the machine
    machine[vas_location] = vas_resources
    machine[vbs_location] = vbs_resources


def _step(vertices, d_limit, temperature, placements, l2v, v2n,
          vertices_resources, fixed_vertices, machine, has_wrap_around_links,
          random):
    """Attempt a single swap operation: the kernel of the Simulated Annealing
    algorithm.

    Parameters
    ----------
    vertices : [vertex, ...]
        The set of *movable* vertices.
    d_limit : int
        The maximum distance over-which swaps are allowed.
    temperature : float > 0.0 or None
        The temperature (i.e. likelihood of accepting a non-advantageous swap).
        Higher temperatures mean higher chances of accepting a swap.
    placements : {vertex: (x, y), ...}
        The positions of all vertices, will be updated if a swap is made.
    l2v : {(x, y): [vertex, ...], ...}
        Lookup from chip to vertices, will be updated if a swap is made.
    v2n : {vertex: [:py:class:`rig.netlist.Net`, ...], ...}
        Lookup from vertex to all nets that vertex is in.
    vertices_resources : {vertex: {resource: value, ...}, ...}
    fixed_vertices : {vertex, ...}
        The set of vertices which must not be moved.
    machine : :py:class:`rig.place_and_route.Machine`
        Describes the state of the machine including the resources actually
        available on each chip given the current placements. Updated if a swap
        is made.
    has_wrap_around_links : bool
        Should the placements attempt to make use of wrap-around links?
    random : :py:class:`random.Random`
        The random number generator to use.

    Returns
    -------
    (swapped, delta)
        swapped is a boolean indicating if a swap was made.

        delta is a float indicating the change in cost resulting from the swap
        (or 0.0 when no swap is made).
    """
    # Special case: If the machine is a singleton, no swaps can be made so just
    # terminate.
    if machine.width == 1 and machine.height == 1:
        return (False, 0.0)

    # Select a vertex to swap at random
    src_vertex = random.choice(vertices)

    # Select a random (nearby) location to swap the vertex with. Note: this is
    # guaranteed to be different from the selected vertex, otherwise the swap
    # cannot change the cost of the placements.
    # XXX: Does not consider hexagonal properties of the system!
    src_location = placements[src_vertex]
    dst_location = src_location
    while dst_location == src_location:
        if has_wrap_around_links:
            dst_location = tuple(random.randint(v - d_limit,
                                                v + d_limit) % limit
                                 for v, limit
                                 in [(src_location[0], machine.width),
                                     (src_location[1], machine.height)])
        else:
            dst_location = tuple(random.randint(max(v - d_limit, 0),
                                                min(v + d_limit, limit-1))
                                 for v, limit
                                 in [(src_location[0], machine.width),
                                     (src_location[1], machine.height)])

    # If we've inadvertently selected a dead chip to swap to, abort the swap.
    if dst_location not in machine:
        return (False, 0.0)

    # Find out which vertices (if any) must be swapped out of the destination
    # to make room for the vertex we're moving.
    src_resources = vertices_resources[src_vertex]
    dst_vertices = _get_candidate_swap(src_resources, dst_location,
                                       l2v, vertices_resources,
                                       fixed_vertices, machine)

    # The destination simply isn't big enough (no matter how many vertices at
    # the destination are moved), abort the swap.
    if dst_vertices is None:
        return (False, 0.0)

    # Make sure that any vertices moved out of the destination will fit in the
    # space left in the source location. If there isn't enough space, abort the
    # swap.
    resources = machine[src_location]
    resources = add_resources(resources, src_resources)
    for dst_vertex in dst_vertices:
        resources = subtract_resources(resources,
                                       vertices_resources[dst_vertex])
    if overallocated(resources):
        return (False, 0.0)

    # Work out the cost of the nets involved *before* swapping
    cost_before = _vertex_net_cost(src_vertex, v2n, placements,
                                   has_wrap_around_links, machine)
    for dst_vertex in dst_vertices:
        cost_before += _vertex_net_cost(dst_vertex, v2n, placements,
                                        has_wrap_around_links, machine)

    # Swap the vertices
    _swap([src_vertex], src_location,
          dst_vertices, dst_location,
          l2v, vertices_resources, placements, machine)

    # Work out the new cost
    cost_after = _vertex_net_cost(src_vertex, v2n, placements,
                                  has_wrap_around_links, machine)
    for dst_vertex in dst_vertices:
        cost_after += _vertex_net_cost(dst_vertex, v2n, placements,
                                       has_wrap_around_links, machine)

    # If the swap was beneficial, keep it, otherwise keep it with a probability
    # related to just how bad the cost change is is and the temperature.
    delta = cost_after - cost_before
    if delta <= 0.0 or random.random() < math.exp(-delta/temperature):
        # Keep the swap!
        return (True, delta)
    else:
        # Revert the swap
        _swap([src_vertex], dst_location,
              dst_vertices, src_location,
              l2v, vertices_resources, placements, machine)
        return (False, 0.0)
