"""A greedy vertex-ordering heuristic for a sequential placer."""

from collections import deque, defaultdict

from rig.place_and_route.place.sequential import place as sequential_place


def breadth_first_vertex_order(vertices_resources, nets):
    """A generator which iterates over a set of vertices in a breadth-first
    order in terms of connectivity.

    For use as a vertex ordering for the sequential placer.
    """
    # Special case: no vertices, just stop immediately
    if len(vertices_resources) == 0:
        return

    # Enumerate the set of nets attached to each vertex
    vertex_neighbours = defaultdict(set)
    for net in nets:
        # Note: Iterating over a Net object produces the set of vertices
        # involved in the net.
        vertex_neighbours[net.source].update(net)
        for sink in net.sinks:
            vertex_neighbours[sink].update(net)

    # Perform a breadth-first iteration over the vertices.
    unplaced_vertices = set(vertices_resources)
    vertex_queue = deque()
    while vertex_queue or unplaced_vertices:
        if not vertex_queue:
            vertex_queue.append(unplaced_vertices.pop())
        vertex = vertex_queue.popleft()

        yield vertex

        vertex_queue.extend(v for v in vertex_neighbours[vertex]
                            if v in unplaced_vertices)
        unplaced_vertices.difference_update(vertex_neighbours[vertex])


def place(vertices_resources, nets, machine, constraints, chip_order=None):
    """Places vertices in breadth-first order onto chips in the machine.

    This is a thin wrapper around the :py:func:`sequential
    <rig.place_and_route.place.sequential.place>` placement algorithm which
    uses the :py:func:`breadth_first_vertex_order` vertex ordering.

    Parameters
    ----------
    chip_order : None or iterable
        The order in which chips should be tried as a candidate location for a
        vertex. See the :py:func:`sequential
        <rig.place_and_route.place.sequential.place>` placer's argument of the
        same name.
    """
    return sequential_place(vertices_resources, nets,
                            machine, constraints,
                            breadth_first_vertex_order(vertices_resources,
                                                       nets),
                            chip_order)
