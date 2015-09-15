"""An experimental simulated-annealing based placer."""

import math
import logging

# This is renamed to ensure that all function correctly use the random number
# generator passed into them.
import random as default_random

from six import iteritems, next

from rig.place_and_route.constraints import \
    LocationConstraint, ReserveResourceConstraint

from rig.place_and_route.exceptions import \
    InvalidConstraintError, InsufficientResourceError

from rig.place_and_route.place.utils import \
    add_resources, subtract_resources, overallocated, \
    apply_reserve_resource_constraint, apply_same_chip_constraints, \
    finalise_same_chip_constraints


"""
This logger is used by the annealing algorithm to indicate progress.
"""
logger = logging.getLogger(__name__)


def _initial_placement(movable_vertices, vertices_resources, machine, random):
    """For internal use. Produces a random, sequential initial placement,
    updating the resource availabilities of every core in the supplied machine.

    Parameters
    ----------
    movable_vertices : [vertex, ...]
        A list of the vertices to be given a random initial placement.
    vertices_resources : {vertex: {resource: value, ...}, ...}
    machine : :py:class:`rig.machine.Machine`
        A machine object describing the machine into which the vertices should
        be placed.

        All chips hosting fixed vertices should have a chip_resource_exceptions
        entry which accounts for the allocated resources.

        When this function returns, the machine.chip_resource_exceptions will
        be updated to account for the resources consumed by the initial
        placement of movable vertices.
    random : :py:class`random.Random`
        The random number generator to use

    Returns
    -------
    {vertex: (x, y), ...}
        For all movable_vertices.

    Raises
    ------
    InsufficientResourceError
    InvalidConstraintError
    """
    # Initially fill chips in the system in a random order
    locations = list(machine)
    random.shuffle(locations)
    location_iter = iter(locations)

    # Greedily place the vertices in a random order
    random.shuffle(movable_vertices)
    vertex_iter = iter(movable_vertices)

    placement = {}
    try:
        location = next(location_iter)
    except StopIteration:
        raise InsufficientResourceError("No working chips in system.")
    while True:
        # Get a vertex to place
        try:
            vertex = next(vertex_iter)
        except StopIteration:
            # All vertices have been placed
            break

        # Advance through the set of available locations until we find a chip
        # where the vertex fits
        while True:
            resources_if_placed = subtract_resources(
                machine[location], vertices_resources[vertex])

            if overallocated(resources_if_placed):
                # The vertex won't fit on this chip, move onto the next chip
                try:
                    location = next(location_iter)
                    continue
                except StopIteration:
                    raise InsufficientResourceError(
                        "Ran out of chips while attempting to place vertex "
                        "{}".format(vertex))
            else:
                # The vertex fits: record the resources consumed and move on to
                # the next vertex.
                placement[vertex] = location
                machine[location] = resources_if_placed
                break

    return placement


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
    machine : :py:class:`rig.machine.Machine`

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
                net.weight)
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

        return ((x2 - x1) + (y2 - y1)) * float(net.weight)


def _vertex_net_cost(vertex, v2n, placements, has_wrap_around_links, machine):
    """Get the total cost of the nets connected to the given vertex.

    Parameters
    ----------
    vertex
        The vertex whose nets we're interested in.
    v2n : {vertex: [:py:class:`rig.netlist.Net`, ...], ...}
    placements : {vertex: (x, y), ...}
    has_wrap_around_links : bool
    machine : :py:class:`rig.machine.Machine`

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
    fixed_vertices : {vertex: (x, y), ...}
    machine : :py:class:`rig.machine.Machine`

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
    machine : :py:class:`rig.machine.Machine`
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
    fixed_vertices : {vertex: (x, y), ...}
        The set of vertices which must not be moved.
    machine : :py:class:`rig.machine.Machine`
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


def place(vertices_resources, nets, machine, constraints,
          effort=1.0, random=default_random, on_temperature_change=None):
    """A flat Simulated Annealing based placement algorithm.

    This placement algorithm uses simulated annealing directly on the supplied
    problem graph with the objective of reducing wire lengths (and thus,
    indirectly, the potential for congestion). Though computationally
    expensive, this placer produces relatively good placement solutions.

    The annealing temperature schedule used by this algorithm is taken from
    "VPR: A New Packing, Placement and Routing Tool for FPGA Research" by
    Vaughn Betz and Jonathan Rose from the "1997 International Workshop on
    Field Programmable Logic and Applications".

    This algorithm is written in pure Python and is not highly optimised for
    performance.

    This algorithm produces INFO level logging information describing the
    progress made by the algorithm.

    .. warning:
        This algorithm does not attempt to produce good solutions to the
        bin-packing problem of optimally fitting vertices into chips and it may
        fail if a good placement requires good bin packing.

    Parameters
    ----------
    effort : float
        A scaling factor for the number of iterations the algorithm should run
        for. 1.0 is probably about as low as you'll want to go in practice and
        runtime increases linearly as you increase this parameter.
    random : :py:class:`random.Random`
        A Python random number generator. Defaults to ``import random`` but can
        be set to your own instance of :py:class:`random.Random` to allow you
        to control the seed and produce deterministic results. For results to
        be deterministic, vertices_resources must be supplied as an
        :py:class:`collections.OrderedDict`.
    on_temperature_change : callback_function or None
        An (optional) callback function which is called every time the
        temperature is changed. This callback can be used to provide status
        updates

        The callback function is passed the following arguments:

        * ``iteration_count``: the number of iterations the placer has
          attempted (integer)
        * ``placements``: The current placement solution.
        * ``cost``: the weighted sum over all nets of bounding-box size.
          (float)
        * ``acceptance_rate``: the proportion of iterations which have resulted
          in an accepted change since the last callback call. (float between
          0.0 and 1.0)
        * ``temperature``: The current annealing temperature. (float)
        * ``distance_limit``: The maximum distance any swap may be made over.
          (integer)

        If the callback returns False, the anneal is terminated immediately and
        the current solution is returned.
    """
    # Special case: just return immediately when there's nothing to place
    if len(vertices_resources) == 0:
        return {}

    # Within the algorithm we modify the resource availability values in the
    # machine to account for the effects of the current placement. As a result,
    # an internal copy of the structure must be made.
    machine = machine.copy()

    # Determine if the system has wrap around links (and thus whether placement
    # should try to use them).
    has_wrap_around_links = machine.has_wrap_around_links()

    # {vertex: (x, y), ...} gives the location of all vertices whose position
    # is fixed by a LocationConstraint.
    fixed_vertices = {}

    # Handle constraints
    vertices_resources, nets, constraints, substitutions = \
        apply_same_chip_constraints(vertices_resources, nets, constraints)
    for constraint in constraints:
        if isinstance(constraint, LocationConstraint):
            # Location constraints are handled by recording the set of fixed
            # vertex locations and subtracting their resources from the chips
            # they're allocated to. These vertices will then not be added to
            # the internal placement data structure to prevent annealing from
            # moving them. They will be re-introduced at the last possible
            # moment.
            location = constraint.location
            if location not in machine:
                raise InvalidConstraintError(
                    "Chip requested by {} unavailable".format(machine))
            vertex = constraint.vertex

            # Record the constrained vertex's location
            fixed_vertices[vertex] = location

            # Make sure the vertex fits at the requested location (updating the
            # resource availability after placement)
            resources = vertices_resources[vertex]
            machine[location] = subtract_resources(machine[location],
                                                   resources)
            if overallocated(machine[location]):
                raise InsufficientResourceError(
                    "Cannot meet {}".format(constraint))
        elif isinstance(constraint,  # pragma: no branch
                        ReserveResourceConstraint):
            apply_reserve_resource_constraint(machine, constraint)

    # Initially randomly place the movable vertices
    movable_vertices = [v for v in vertices_resources
                        if v not in fixed_vertices]
    placements = _initial_placement(movable_vertices,
                                    vertices_resources,
                                    machine, random)

    # Include the fixed vertices
    placements.update(fixed_vertices)

    # Special cases where no placement effort is required:
    # * No movable vertices
    # * No effort is to be made
    # * There are no nets (and moving things has no effect)
    if len(movable_vertices) == 0 or effort == 0.0 or len(nets) == 0:
        finalise_same_chip_constraints(substitutions, placements)
        return placements

    # Location-to-Vertices: A lookup {(x, y): [vertex, ...], ...} giving the
    # set of vertices on a given chip.  Chips which are not in the machine are
    # excluded from this lookup.
    l2v = {xy: [] for xy in machine}
    for vertex, location in iteritems(placements):
        l2v[location].append(vertex)

    # Vertices-to-Nets: A lookup {vertex: [Net, ...], ...}, gives a list of
    # nets of which the given vertex is a member.
    v2n = {v: [] for v in vertices_resources}
    for net in nets:
        for v in net:
            if net not in v2n[v]:
                v2n[v].append(net)

    # Specifies the maximum distance any swap can span. Initially consider
    # swaps that span the entire machine.
    d_limit = max(machine.width, machine.height)

    # Determine initial temperature according to the heuristic used by VPR: 20
    # times the standard deviation of len(movable_vertices) random swap costs.
    # Note: though this would be better implemented by Numpy, it is implemented
    # in pure Python to allow this module to run under pypy.
    deltas = []
    for _ in range(len(movable_vertices)):
        _, delta = _step(movable_vertices,
                         # During initial pass, work at very high temperature
                         # since we want to get the average swap cost
                         # (including bad ones)
                         int(d_limit), 1.e1000,
                         placements, l2v, v2n,
                         vertices_resources, fixed_vertices, machine,
                         has_wrap_around_links, random)
        deltas.append(delta)
    mean = sum(deltas) / float(len(deltas))
    std = math.sqrt(sum((v-mean)**2 for v in deltas) / len(deltas))
    temperature = 20.0 * std

    # The number of swap-attempts between temperature changes is selected by
    # the heuristic used by VPR. This value is scaled linearly by the effort
    # parameter.
    num_iterations = max(1, int(effort * len(vertices_resources)**1.33))

    logger.info("Initial placement temperature: %0.1f", temperature)

    # Counter for the number of swap attempts made (used for diagnostic
    # purposes)
    iteration_count = 0

    # Holds the total cost of the current placement. This default value chosen
    # to ensure the loop below iterates at least once.
    current_cost = 0.0

    # The annealing algorithm runs until a heuristic termination condition
    # (taken from VPR) is hit. The heuristic waits until the temperature falls
    # below a small fraction of the average net cost.
    while temperature > (0.005 * current_cost) / len(nets):
        # Run an iteration at the current temperature
        num_accepted = 0
        for _ in range(num_iterations):
            accepted, _ = _step(movable_vertices,
                                int(d_limit), temperature,
                                placements, l2v, v2n,
                                vertices_resources, fixed_vertices, machine,
                                has_wrap_around_links, random)
            num_accepted += 1 if accepted else 0

        # The ratio of accepted-to-not-accepted changes
        r_accept = num_accepted / float(num_iterations)

        # Work out the new total net cost for the current placement.
        current_cost = 0.0
        for net in nets:
            current_cost += _net_cost(net, placements, has_wrap_around_links,
                                      machine)

        # Special case: Can't do better than 0 cost! This is a special case
        # since the normal termination condition will not terminate if the cost
        # doesn't drop below 0.
        if current_cost == 0:
            break

        # The temperature is reduced by a factor heuristically based on the
        # acceptance rate. The schedule below attempts to maximise the time
        # spent at temperatures where a large portion (but not all) of changes
        # are being accepted. If lots of changes are being accepted (e.g.
        # during high-temperature periods) then most of them are likely not to
        # be beneficial. If few changes are being accepted, we're probably
        # pretty close to the optimal placement.
        if r_accept > 0.96:
            alpha = 0.5
        elif r_accept > 0.8:
            alpha = 0.9
        elif r_accept > 0.15:
            alpha = 0.95
        else:
            alpha = 0.8
        temperature = alpha * temperature

        # According to:
        # * M. Huang, F. Romeo, and A. Sangiovanni-Vincentelli, "An Efficient
        #   General Cooling Schedule for Simulated Annealing" ICCAD, 1986, pp.
        #   381 - 384 and J. Lam
        # * J. Delosme, "Performance of a New Annealing Schedule" DAC, 1988,
        #   pp. 306 - 311.
        # It is desirable to keep the acceptance ratio as close to 0.44 for as
        # long as possible. As a result, when r_accept falls below this we can
        # help increase the acceptance rate by reducing the set of possible
        # swap candidates based on the observation that near the end of
        # placement, most things are near their optimal location and thus long
        # distance swaps are unlikely to be useful.
        d_limit *= 1.0 - 0.44 + r_accept
        d_limit = min(max(d_limit, 1), max(machine.width, machine.height))

        iteration_count += num_iterations
        logger.debug("After %d iterations cost is %0.1f, "
                     "swap acceptance rate is %0.1f%%, "
                     "temperature changing to %0.3f, "
                     "swap distance limit now %d.",
                     iteration_count, current_cost,
                     r_accept*100, temperature, d_limit)

        # Call the user callback before the next iteration, terminating if
        # requested.
        if (on_temperature_change is not None and
                on_temperature_change(iteration_count,
                                      placements,
                                      current_cost,
                                      r_accept,
                                      temperature,
                                      d_limit) is False):
            break

    logger.info("Anneal terminated after %d iterations with final cost %0.1f.",
                iteration_count, current_cost)

    finalise_same_chip_constraints(substitutions, placements)

    return placements
