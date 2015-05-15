"""An experimental simulated-annealing based placer."""

from six import iteritems, iterkeys, itervalues

import random
import math
import heapq

from rig.place_and_route.place.hilbert import hilbert

from rig.place_and_route.exceptions import \
    InvalidConstraintError, InsufficientResourceError

from rig.place_and_route.place.utils import \
    add_resources, subtract_resources, overallocated, \
    resources_after_reservation


def _initial_placement(movable_vertices, vertices_resources, machine):
    """For internal use. Produces a random, sequential initial placement.
    
    Also updates the resource availability of each chip in the machine.
    """
    # Allocate chips along a Hilbert curve large enough to cover the whole
    # system
    max_dimen = max(machine.width, machine.height)
    hilbert_levels = int(math.ceil(math.log(max_dimen, 2.0))) if max_dimen >= 1 else 0
    location_iter = hilbert(hilbert_levels)
    
    placement = {}
    random.shuffle(movable_vertices)
    vertex_iter = iter(movable_vertices)
    location = next(location_iter)
    while True:
        # Get a vertex to place
        try:
            vertex = next(vertex_iter)
        except StopIteration:
            break
        
        # Advance through the set of available locations until we can find a
        # chip where the vertex fits
        while True:
            try:
                if location not in machine:
                    location = next(location_iter)
                    continue
                
                resources_if_placed = subtract_resources(
                    machine[location], vertices_resources[vertex])
                
                if overallocated(resources_if_placed):
                    # Didn't fit, try the next chip
                    location = next(location_iter)
                    continue
            except StopIteration:
                raise InsufficientResourceError(
                    "Ran out of chips while attempting to place vertex "
                    "{}".format(vertex))
            else:
                # The vertex fit, note the consumed resources and move on to the
                # next vertex
                placement[vertex] = location
                machine[location] = resources_if_placed
                break
    
    return placement


def _net_bb(net, placement):
    """Get the bounding-box (x1,y1, x2,y2) for the vertices in a given net."""
    # XXX: This does not account for the hexagonal, nor torus-properties of the
    # SpiNNaker topology.
    x1, y1 = x2, y2 = placement[net.source]
    for vertex in net.sinks:
        x, y = placement[vertex]
        x1 = x if x < x1 else x1
        y1 = y if y < y1 else y1
        x2 = x if x > x2 else x2
        y2 = y if y > y2 else y2
    return (x1, y1, x2, y2)


def _vertex_net_cost(vertex, v2n, placement):
    """Get the total cost of the nets connected to the given vertex."""
    total_cost = 0.0
    for net in v2n[vertex]:
        x1, y1, x2, y2 = _net_bb(net, placement)
        net_cost = abs(x1 - x2) + abs(y1 - y2)
        
        total_cost += net_cost * net.weight
    
    return total_cost


def _get_candidate_swap(resources, location, l2v, vertices_resources,
                        fixed_vertices, machine):
    """Given a chip location, select a set of vertices which would have to be
    moved elsewhere to accommodate the arrival of the specified set of
    resources.
    
    Parameters
    ----------
    resources
        The amount of resources which are required at the specified location.
    location : (x, y)
        The chip coordinates from which to find a space.
    
    Returns
    -------
    [Vertex, ...] or None
        If None, the situation is impossible.
        If a (possibly empty) list, gives the set of vertices which should be
        removed from the specified location to make room.
    """
    chip_resources = machine[location]
    
    vertices = l2v[location]
    
    to_move = []
    i = 0
    while overallocated(subtract_resources(chip_resources, resources)):
        if i >= len(vertices):
            # Run out of vertices to remove from this chip, fail
            return None
        
        if vertices[i] in fixed_vertices:
            # Don't try moving fixed vertices
            i += 1
            continue
        else:
            chip_resources = add_resources(chip_resources,
                                           vertices_resources[vertices[i]])
            to_move.append(vertices[i])
            i += 1
    
    return to_move


def _swap(vas, vas_location, vbs, vbs_location, l2v, vertices_resources, placement, machine):
    """Swap the positions of two sets of vertices: vas and vbs at locations
    vas_location2v and vbs_location2v."""
    vas_location2v = l2v[vas_location]
    vbs_location2v = l2v[vbs_location]
    
    vas_resources = machine[vas_location]
    vbs_resources = machine[vbs_location]
    
    for va in vas:
        placement[va] = vbs_location
        vas_location2v.remove(va)
        vbs_location2v.append(va)
        
        resources = vertices_resources[va]
        vas_resources = add_resources(vas_resources, resources)
        vbs_resources = subtract_resources(vbs_resources, resources)
    
    for vb in vbs:
        placement[vb] = vas_location
        vbs_location2v.remove(vb)
        vas_location2v.append(vb)
        
        resources = vertices_resources[vb]
        vas_resources = subtract_resources(vas_resources, resources)
        vbs_resources = add_resources(vbs_resources, resources)
    
    machine[vas_location] = vas_resources
    machine[vbs_location] = vbs_resources


def _step(vertices, d_limit, temperature, placement, l2v, v2n, vertices_resources, fixed_vertices, machine):
    """Attempt a single swap operation.
    
    Parameters
    ----------
    vertices : [vertex, ...]
    d_limit : int
        The maximum distance over-which swaps are allowed.
    temperature : float > 0.0 or None
        The temperature (i.e. likelihood of accepting a non-advantageous swap).
    
    Returns
    -------
    (swapped, delta)
        swapped is a boolean indicating if the swap made was kept
        
        delta is a float indicating the change in cost resulting from the swap
        (or 0.0 when no swap is made).
    """
    # XXX: Does not consider hexagonal/torus properties of the system!
    
    # Select a vertex to swap at random
    src_vertex = random.choice(vertices)
    
    # Select a random (nearby) location to swap the vertex with
    src_location = placement[src_vertex]
    dst_location = src_location
    while dst_location == src_location:
        dst_location = tuple(random.randint(max(v-(d_limit), 0),
                                            min(v+(d_limit), limit-1))
                             for v, limit
                             in [(src_location[0], machine.width),
                                 (src_location[1], machine.height)])
    
    # The selected location is dead/not in the machine
    if dst_location not in machine:
        return (False, 0.0)
    
    # Decide what vertex to swap with at the destination
    src_resources = vertices_resources[src_vertex]
    dst_vertices = _get_candidate_swap(src_resources, dst_location,
                                       l2v, vertices_resources,
                                       fixed_vertices, machine)
    
    # The destination vertex cannot fit the source vertex
    if dst_vertices is None:
        return (False, 0.0)
    
    # Can we fit the vertices to be moved from the destination in the space in
    # the source when we move the source vertex?
    resources = machine[src_location]
    resources = add_resources(resources, src_resources)
    for dst_vertex in dst_vertices:
        resources = subtract_resources(resources,
                                       vertices_resources[dst_vertex])
    if overallocated(resources):
        # There isn't enough space in the source to make the swap.
        return (False, 0.0)
    
    # Work out the cost of the nets involved *before* swapping
    cost_before = _vertex_net_cost(src_vertex, v2n, placement)
    for dst_vertex in dst_vertices:
        # XXX: Counts the cost due to any source-connected nets twice!
        cost_before += _vertex_net_cost(dst_vertex, v2n, placement)
    
    # Swap the vertices
    _swap([src_vertex], src_location,
          dst_vertices, dst_location,
          l2v, vertices_resources, placement, machine)
    
    # Work out the new cost
    cost_after = _vertex_net_cost(src_vertex, v2n, placement)
    for dst_vertex in dst_vertices:
        # XXX: Counts the cost due to any source-connected nets twice!
        cost_after += _vertex_net_cost(dst_vertex, v2n, placement)
    
    # Decide whether to revert the swap or not
    delta = cost_after - cost_before
    if delta > 0.0 and random.random() > math.exp(-delta/temperature):
        # Revert the swap
        _swap([src_vertex], dst_location,
              dst_vertices, src_location,
              l2v, vertices_resources, placement, machine)
        return (False, 0.0)
    else:
        # Keep the swap!
        return (True, delta)


def place(vertices_resources, nets, machine, constraints, effort=1.0):
    """A flat Simulated Annealing based placement algorithm.
    
    This algorithm uses simulated annealing directly on the supplied problem
    graph with the objective of reducing wire lengths (and thus potential for
    congestion).
    
    .. warning:
        This algorithm does not attempt to produce good solutions to the
        bin-packing problem of fitting vertices into chips and it may fail if a
        good placement requires good bin packing.
    
    Parameters
    ----------
    effort : float
        A scaling factor for the number of iterations the algorithm should run
        for. 1.0 is probably about as low as you'll want to go in practice and
        runtime increases linearly as you increase this parameter.
    """
    # Create a modified machine which accounts for any constraints
    machine = machine.copy()
    
    # A dictionary giving the positions of all fixed vertices.
    fixed_vertices = {}
    
    # Handle constraints
    for constraint in constraints:
        if isinstance(constraint, LocationConstraint):
            # Location constraints are handled by recording the set of fixed
            # vertex locations and subtracting their resources from the chips
            # they're allocated to. These vertices will then not be added to the
            # internal placement data structure to prevent annealing from moving
            # them. They will be re-introduced at the last possible moment.
            location = constraint.location
            if location not in machine:
                raise InvalidConstraintError(
                    "Chip requested by {} unavailable".format(machine))
            vertex = constraint.vertex
            
            # Record the constrained vertex's location
            fixed_vertices[vertex] = location
            
            # Discount the required resources from the specified chip
            resources = vertices_resources[vertex]
            machine[loc] = subtract_resources(machine[loc], resources)
            if overallocated(machine[loc]):
                raise InsufficientResourceError(
                    "Cannot meet {}".format(constraint))
        elif isinstance(constraint, ReserveResourceConstraint):
            # Reserved resources are simply subtracted from the numbers
            # supplied.
            if constraint.location is None:
                # Global resource reservation
                machine.chip_resources \
                    = resources_after_reservation(
                        machine.chip_resources, constraint)
                for location in machine.chip_resource_exceptions:
                    machine.chip_resource_exceptions[location] \
                        = resources_after_reservation(
                            machine.chip_resource_exceptions[location],
                            constraint)
            else:
                # Compensate for reserved resources at a specified location
                machine[constraint.location] = resources_after_reservation(
                    machine[constraint.location], constraint)
    
    # Initially randomly place the movable vertices
    movable_vertices = [v for v in vertices_resources
                        if v not in fixed_vertices]
    placement = _initial_placement(movable_vertices,
                                   vertices_resources,
                                   machine)
    placement.update(fixed_vertices)
    
    # Location-to-Vertices: A lookup {(x, y): [vertex, ...], ...} giving the set
    # of vertices on a given chip.  Positions which are not usable are excluded
    # from this lookup.
    l2v = {(x, y): []
           for x in range(machine.width)
           for y in range(machine.height)
           if (x, y) in machine}
    for vertex, location in iteritems(placement):
        l2v[location].append(vertex)
    
    # Vertices-to-Nets: A lookup {vertex: [Net, ...], ...}, gives a list of nets
    # of which the given vertex is a member.
    v2n = {v: [] for v in vertices_resources}
    for net in nets:
        for v in net:
            if net not in v2n[v]:
                v2n[v].append(net)
    
    # Initially consider swaps the entire span of the machine away
    d_limit = max(machine.width, machine.height)
    
    # Determine initial temperature
    deltas = []
    for _ in range(len(movable_vertices)):
        _, delta = _step(movable_vertices,
                         # During initial pass, work at very high temperature
                         # since we want to get the average swap cost (including
                         # bad ones)
                         int(d_limit), 1.e1000,
                         placement, l2v, v2n,
                         vertices_resources, fixed_vertices, machine)
        deltas.append(delta)
    mean = sum(deltas) / float(len(deltas))
    std = math.sqrt(sum((v-mean)**2 for v in deltas) / len(deltas))
    temperature = 20.0 * std
    
    # Determine number of iterations per temperature
    num_iterations = int(effort * len(vertices_resources)**1.33)
    
    import sys
    print("Starting temperature: {} (iterations per temp: {})".format(
        temperature, num_iterations))
    sys.stdout.flush()
    
    current_cost = 0.0
    while effort > 0.0 and temperature > 0.005 * current_cost / len(movable_vertices):
        # Run an iteration at the current temperature
        num_kept = 0
        for _ in range(num_iterations):
            kept, _ = _step(movable_vertices,
                            int(d_limit), temperature,
                            placement, l2v, v2n,
                            vertices_resources, fixed_vertices, machine)
            num_kept += 1 if kept else 0
        
        # Work out how the temperature should be changed
        r_accept = num_kept / float(num_iterations)
        if r_accept > 0.96: alpha = 0.5
        elif r_accept > 0.8: alpha = 0.9
        elif r_accept > 0.15: alpha = 0.95
        else: alpha = 0.8
        temperature = alpha * temperature
    
        # Update d_limit
        d_limit *= 1.0 - 0.44 + r_accept
        d_limit = min(max(d_limit, 1), max(machine.width, machine.height))
    
        # End cost
        current_cost = 0
        for net in nets:
            x1, y1, x2, y2 = _net_bb(net, placement)
            current_cost += (abs(x1-x2) + abs(y1-y2)) * net.weight
        
        print("Iteration ended with cost {}".format(current_cost))
        sys.stdout.flush()
    
    return placement


if __name__=="__main__":
    from rig.machine import Machine, Cores
    from rig.netlist import Net
    
    random.seed(2)
    
    
    w, h = 10, 10
    machine = Machine(10, 10, chip_resources={Cores: 1})
    ideal_placement = {(x, y): object()
                       for x in range(w)
                       for y in range(h)}
    ideal_vertices_position = {v: xy for xy, v in iteritems(ideal_placement)}
    
    vertices = list(itervalues(ideal_placement))
    
    def i(x, y):
        if x >= w or x < 0 or y >= h or y < 0:
            return None
        else:
            return ideal_placement[(x%w, y%h)]
    nets = []
    ## Nearest-neighbour connectivity
    #nets += [Net(i(x, y),
    #             [xy for xy in [i(x+1,y+1), # Top
    #                            i(x+0,y+1),
    #                            i(x-1,y+1), # Left
    #                            i(x-1,y+0),
    #                            i(x-1,y-1), # Bottom
    #                            i(x+0,y-1),
    #                            i(x+1,y-1), # Right
    #                            i(x+1,y+0),
    #                            ]
    #              if xy is not None])
    #         for x in range(w)
    #         for y in range(h)]
    
    ## Random connectivity
    #fan_out = 1, 5
    #nets += [Net(v, random.sample(vertices, random.randint(*fan_out)))
    #         for v in vertices]
    
    # Thick pipeline connectivity
    n_vertices = len(vertices)
    thickness = 5
    nets += [Net(vertices[i],
                 vertices[(i//thickness + 1)*thickness: (i//thickness + 2)*thickness])
             for i in range(n_vertices)
             if i + thickness < n_vertices]
    
    placement = place({v: {Cores: 1} for v in vertices},
                      nets, machine, [], 1.0)
    
    # Save the output graph as a graphviz file
    with open("/tmp/graph.dot", "w") as f:
        f.write("digraph {\n")
        
        # Set style
        f.write("node [shape=circle label=\"\"]\n")
        
        # Record placements
        for vertex, position in iteritems(placement):
            f.write("n{} [pos=\"{},{}!\"]\n".format(
                id(vertex), position[0], position[1]))
        
        # Print nets
        for net in nets:
            for sink in net.sinks:
                f.write("n{} -> n{}\n".format(
                    id(net.source),
                    id(sink)))
        
        f.write("}")
    
    # Check the placement is valid
    from collections import defaultdict
    verts_on_chip = defaultdict(lambda: 0)
    assert len(placement) == len(ideal_placement)
    for vertex, xy in iteritems(placement):
        verts_on_chip[xy] += 1
        assert verts_on_chip[xy] <= machine.chip_resources[Cores]
