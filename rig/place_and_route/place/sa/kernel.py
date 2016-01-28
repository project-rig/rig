# pragma: no cover

"""General interface for a SA algorithm kernel."""


class Kernel(object):
    """A general API for a SA algorithm kernel."""

    def __init__(self, vertices_resources, movable_vertices, fixed_vertices,
                 initial_placements, nets, machine, random, **kwargs):
        """Initialise the algorithm kernel with a placement problem.

        Placement problems are described simillarly to the normal Rig fashion
        with the main exception that no
        :py:mod:`~rig.place_and_route.constraints` may be given.

        A kernel need not be able to handle the following special-case
        placement problems:

        * Where no resource types exist
        * For 1x1 machines (or smaller...)
        * With no vertices are movable
        * Only nets with zero weights
        * Only nets with < 2 uniqe vertices

        Parameters
        ----------
        vertices_resources : {vertex: {resource: value, ...}, ...}
            The resources consumed by all vertices.
        movable_vertices : {vertex, ...}
            Identifies all movable vertices.
        fixed_vertices : {vertex, ...}
            Identifies all non-movable vertices.
        initial_placements : {vertex: (x, y), ...}
            Gives the initial location of all vertices.
        nets : [:py:class:`~rig.netlist.Net`, ...]
            The nets which connect all movable and fixed vertices.
        machine : :py:class:`~rig.place_and_route.Machine`
            This machine must have the resources consumed by the initial
            placement subtracted from each chip. This object may be modified at
            will.
        random : :py:class:`random.Random`
            The random number generator to use.
        """
        raise NotImplementedError()

    def run_steps(self, num_steps, distance_limit, temperature):
        """Attempt num_steps swaps.

        Parameters
        ----------
        num_steps : int
            The number of swap attempts to be made.
        distance_limit : int
            The maximum distance over which a swap may be made (as the "radius"
            of a square).
        temperature : float
            The current annealing temperature.

        Returns
        -------
        num_accepted : int
            The number accepted swaps.
        cost : float
            The global cost of the placement after all swaps have been
            completed.
        cost_delta_sd : float
            The standard deviation of the cost changes resulting from each
            swap.
        """
        raise NotImplementedError()

    def get_placements(self):
        """Get the current placement solution.

        Returns
        -------
        {vertex: (x, y), ...}
        """
        raise NotImplementedError()
