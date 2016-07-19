"""The main annealing algorithm loop."""

import math
import logging

# This is renamed to ensure that all function correctly use the random number
# generator passed into them.
import random as default_random

from six import next

from rig.place_and_route.constraints import \
    LocationConstraint, ReserveResourceConstraint

from rig.place_and_route.exceptions import \
    InvalidConstraintError, InsufficientResourceError

from rig.place_and_route.place.utils import \
    subtract_resources, overallocated, \
    apply_reserve_resource_constraint, apply_same_chip_constraints, \
    finalise_same_chip_constraints


# Select a sensible default kernel
try:  # pragma: no cover
    from rig.place_and_route.place.sa.c_kernel \
        import CKernel as default_kernel
except ImportError:  # pragma: no cover
    from rig.place_and_route.place.sa.python_kernel \
        import PythonKernel as default_kernel


"""
This logger is used by the annealing algorithm to indicate progress.
"""
logger = logging.getLogger(__name__.split(".")[-1])


def _initial_placement(movable_vertices, vertices_resources, machine, random):
    """For internal use. Produces a random, sequential initial placement,
    updating the resource availabilities of every core in the supplied machine.

    Parameters
    ----------
    movable_vertices : {vertex, ...}
        A set of the vertices to be given a random initial placement.
    vertices_resources : {vertex: {resource: value, ...}, ...}
    machine : :py:class:`rig.place_and_route.Machine`
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
    movable_vertices = list(v for v in vertices_resources
                            if v in movable_vertices)
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


def place(vertices_resources, nets, machine, constraints,
          effort=1.0, random=default_random, on_temperature_change=None,
          kernel=default_kernel, kernel_kwargs={}):
    """A flat Simulated Annealing based placement algorithm.

    This placement algorithm uses simulated annealing directly on the supplied
    problem graph with the objective of reducing wire lengths (and thus,
    indirectly, the potential for congestion). Though computationally
    expensive, this placer produces relatively good placement solutions.

    The annealing temperature schedule used by this algorithm is taken from
    "VPR: A New Packing, Placement and Routing Tool for FPGA Research" by
    Vaughn Betz and Jonathan Rose from the "1997 International Workshop on
    Field Programmable Logic and Applications".

    Two implementations of the algorithm's kernel are available:

    * :py:class:`~rig.place_and_route.place.sa.python_kernel.PythonKernel` A
      pure Python implementation which is available on all platforms supported
      by Rig.
    * :py:class:`~rig.place_and_route.place.sa.c_kernel.CKernel` A C
      implementation which is typically 50-150x faster than the basic Python
      kernel. Since this implementation requires a C compiler during
      installation, it is an optional feature of Rig. See the
      :py:class:`CKernel's documentation
      <rig.place_and_route.place.sa.c_kernel.CKernel>` for details.

    The fastest kernel installed is used by default and can be manually chosen
    using the ``kernel`` argument.

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
    kernel : :py:class:`~rig.place_and_route.place.sa.kernel.Kernel`
        A simulated annealing placement kernel. A sensible default will be
        chosen based on the available kernels on this machine. The kernel may
        not be used if the placement problem has a trivial solution.
    kernel_kwargs : dict
        Optional kernel-specific keyword arguments to pass to the kernel
        constructor.
    """
    # Special case: just return immediately when there's nothing to place
    if len(vertices_resources) == 0:
        return {}

    # Within the algorithm we modify the resource availability values in the
    # machine to account for the effects of the current placement. As a result,
    # an internal copy of the structure must be made.
    machine = machine.copy()

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
    movable_vertices = {v for v in vertices_resources
                        if v not in fixed_vertices}
    initial_placements = _initial_placement(movable_vertices,
                                            vertices_resources,
                                            machine, random)

    # Include the fixed vertices in initial placement
    initial_placements.update(fixed_vertices)

    # Filter out empty or singleton nets and those weighted as zero since they
    # cannot influence placement.
    nets = [n for n in nets if len(set(n)) > 1 and n.weight > 0.0]

    # Special cases where no placement effort is required:
    # * There is only one chip
    # * There are no resource types to be consumed
    # * No effort is to be made
    # * No movable vertices
    # * There are no nets (and moving things has no effect)
    trivial = ((machine.width, machine.height) == (1, 1) or
               len(machine.chip_resources) == 0 or
               effort == 0.0 or
               len(movable_vertices) == 0 or
               len(nets) == 0)
    if trivial:
        logger.info("Placement has trivial solution. SA not used.")
        finalise_same_chip_constraints(substitutions, initial_placements)
        return initial_placements

    # Intialise the algorithm kernel
    k = kernel(vertices_resources, movable_vertices, set(fixed_vertices),
               initial_placements, nets, machine, random, **kernel_kwargs)

    logger.info("SA placement kernel: %s", kernel.__name__)

    # Specifies the maximum distance any swap can span. Initially consider
    # swaps that span the entire machine.
    distance_limit = max(machine.width, machine.height)

    # Determine initial temperature according to the heuristic used by VPR: 20
    # times the standard deviation of len(movable_vertices) random swap costs.
    # The arbitrary very-high temperature is used to cause "all" swaps to be
    # accepted.
    _0, _1, cost_delta_sd = k.run_steps(len(movable_vertices),
                                        distance_limit,
                                        1e100)
    temperature = 20.0 * cost_delta_sd

    # The number of swap-attempts between temperature changes is selected by
    # the heuristic used by VPR. This value is scaled linearly by the effort
    # parameter.
    num_steps = max(1, int(effort * len(vertices_resources)**1.33))

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
        num_accepted, current_cost, _ = k.run_steps(
            num_steps, int(math.ceil(distance_limit)), temperature)

        # The ratio of accepted-to-not-accepted changes
        r_accept = num_accepted / float(num_steps)

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
        distance_limit *= 1.0 - 0.44 + r_accept
        distance_limit = min(max(distance_limit, 1.0),
                             max(machine.width, machine.height))

        iteration_count += num_steps
        logger.debug("Iteration: %d, "
                     "Cost: %0.1f, "
                     "Kept: %0.1f%%, "
                     "Temp: %0.3f, "
                     "Dist: %d.",
                     iteration_count, current_cost,
                     r_accept*100, temperature, math.ceil(distance_limit))

        # Call the user callback before the next iteration, terminating if
        # requested.
        if on_temperature_change is not None:
            placements = k.get_placements().copy()
            finalise_same_chip_constraints(substitutions, placements)
            ret_val = on_temperature_change(iteration_count,
                                            placements,
                                            current_cost,
                                            r_accept,
                                            temperature,
                                            distance_limit)
            if ret_val is False:
                break

    logger.info("Anneal terminated after %d iterations.", iteration_count)

    placements = k.get_placements()
    finalise_same_chip_constraints(substitutions, placements)

    return placements
