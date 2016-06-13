"""Reverse Cuthill-McKee based placement.
"""

from collections import defaultdict, deque

from six import itervalues

from rig.place_and_route.place.sequential import place as sequential_place
from rig.links import Links
from rig.netlist import Net


def _get_vertices_neighbours(nets):
    """Generate a listing of each vertex's immedate neighbours in an undirected
    interpretation of a graph.

    Returns
    -------
    {vertex: {vertex: weight, ...}), ...}
    """
    zero_fn = (lambda: 0)
    vertices_neighbours = defaultdict(lambda: defaultdict(zero_fn))
    for net in nets:
        if net.weight != 0:
            for sink in net.sinks:
                vertices_neighbours[net.source][sink] += net.weight
                vertices_neighbours[sink][net.source] += net.weight
    return vertices_neighbours


def _dfs(vertex, vertices_neighbours):
    """Generate all the vertices connected to the supplied vertex in
    depth-first-search order.
    """
    visited = set()
    to_visit = deque([vertex])
    while to_visit:
        vertex = to_visit.pop()
        if vertex not in visited:
            yield vertex
            visited.add(vertex)
            to_visit.extend(vertices_neighbours[vertex])


def _get_connected_subgraphs(vertices, vertices_neighbours):
    """Break a graph containing unconnected subgraphs into a list of connected
    subgraphs.

    Returns
    -------
    [set([vertex, ...]), ...]
    """
    remaining_vertices = set(vertices)
    subgraphs = []
    while remaining_vertices:
        subgraph = set(_dfs(remaining_vertices.pop(), vertices_neighbours))
        remaining_vertices.difference_update(subgraph)
        subgraphs.append(subgraph)

    return subgraphs


def _cuthill_mckee(vertices, vertices_neighbours):
    """Yield the Cuthill-McKee order for a connected, undirected graph.

    `Wikipedia
    <https://en.wikipedia.org/wiki/Cuthill%E2%80%93McKee_algorithm>`_ provides
    a good introduction to the Cuthill-McKee algorithm. The RCM algorithm
    attempts to order vertices in a graph such that their adjacency matrix's
    bandwidth is reduced. In brief the RCM algorithm is a breadth-first search
    with the following tweaks:

    * The search starts from the vertex with the lowest degree.
    * Vertices discovered in each layer of the search are sorted by ascending
      order of their degree in the output.

    .. warning::

        This function must not be called on a disconnected or empty graph.

    Returns
    -------
    [vertex, ...]
    """
    vertices_degrees = {v: sum(itervalues(vertices_neighbours[v]))
                        for v in vertices}

    peripheral_vertex = min(vertices, key=(lambda v: vertices_degrees[v]))

    visited = set([peripheral_vertex])
    cm_order = [peripheral_vertex]
    previous_layer = set([peripheral_vertex])
    while len(cm_order) < len(vertices):
        adjacent = set()
        for vertex in previous_layer:
            adjacent.update(vertices_neighbours[vertex])
        adjacent.difference_update(visited)

        visited.update(adjacent)
        cm_order.extend(sorted(adjacent, key=(lambda v: vertices_degrees[v])))
        previous_layer = adjacent

    return cm_order


def rcm_vertex_order(vertices_resources, nets):
    """A generator which iterates over the vertices in Reverse-Cuthill-McKee
    order.

    For use as a vertex ordering for the sequential placer.
    """
    vertices_neighbours = _get_vertices_neighbours(nets)
    for subgraph_vertices in _get_connected_subgraphs(vertices_resources,
                                                      vertices_neighbours):
        cm_order = _cuthill_mckee(subgraph_vertices, vertices_neighbours)
        for vertex in reversed(cm_order):
            yield vertex


def rcm_chip_order(machine):
    """A generator which iterates over a set of chips in a machine in
    Reverse-Cuthill-McKee order.

    For use as a chip ordering for the sequential placer.
    """
    # Convert the Machine description into a placement-problem-style-graph
    # where the vertices are chip coordinate tuples (x, y) and each net
    # represents the links leaving each chip. This allows us to re-use the
    # rcm_vertex_order function above to generate an RCM ordering of chips in
    # the machine.
    vertices = list(machine)
    nets = []
    for (x, y) in vertices:
        neighbours = []
        for link in Links:
            if (x, y, link) in machine:
                dx, dy = link.to_vector()
                neighbour = ((x + dx) % machine.width,
                             (y + dy) % machine.height)

                # In principle if the link to chip is marked as working, that
                # chip should be working. In practice this might not be the
                # case (especially for carelessly hand-defined Machine
                # objects).
                if neighbour in machine:
                    neighbours.append(neighbour)
        nets.append(Net((x, y), neighbours))

    return rcm_vertex_order(vertices, nets)


def place(vertices_resources, nets, machine, constraints):
    """Assigns vertices to chips in Reverse-Cuthill-McKee (RCM) order.

    The `RCM <https://en.wikipedia.org/wiki/Cuthill%E2%80%93McKee_algorithm>`_
    algorithm (in graph-centric terms) is a simple breadth-first-search-like
    heuristic which attempts to yield an ordering of vertices which would yield
    a 1D placement with low network congestion.  Placement is performed by
    sequentially assigning vertices in RCM order to chips, also iterated over
    in RCM order.

    This simple placement scheme is described by Torsten Hoefler and Marc Snir
    in their paper entitled 'Generic topology mapping strategies for
    large-scale parallel architectures' published in the Proceedings of the
    international conference on Supercomputing, 2011.

    This is a thin wrapper around the :py:func:`sequential
    <rig.place_and_route.place.sequential.place>` placement algorithm which
    uses an RCM ordering for iterating over chips and vertices.

    Parameters
    ----------
    breadth_first : bool
        Should vertices be placed in breadth first order rather than the
        iteration order of vertices_resources. True by default.
    """
    return sequential_place(vertices_resources, nets,
                            machine, constraints,
                            rcm_vertex_order(vertices_resources, nets),
                            rcm_chip_order(machine))
