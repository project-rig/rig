"""A simple, non-nonsense, greedy chip resource allocator.

Note that this algorithm is "optimal" in the sense that given any valid
placement, allocation will succeed. This algorithm is thus only unsuitable for
users who care about the order or spacing of resource allocations in the
system.  Some important examples of where users may care about this sort of
thing:

* This algorithm does not align memory allocations to word-aligned regions: it
  doesn't know what memory is!
* This algorithm does not attempt to allocate the same core ranges to specific
  sets of vertices to improve flood-fillability: it does not know what cores or
  flood-fill is!
"""

from collections import defaultdict

from six import iteritems

from ..constraints import ReserveResourceConstraint, AlignResourceConstraint

from ..exceptions import InsufficientResourceError

from .utils import slices_overlap, align


def allocate(vertices_resources, nets, machine, constraints, placements):
    """Allocate resources to vertices on cores arbitrarily using a simple greedy
    algorithm.
    """
    allocation = {}

    # Globally reserved resource ranges {resource, [slice, ...], ...}
    globally_reserved = defaultdict(list)
    # Locally reserved resource ranges {(x, y): {resource, [slice, ...], ...}}
    locally_reserved = defaultdict(lambda: defaultdict(list))

    # Alignment of each resource
    alignments = defaultdict(lambda: 1)

    # Collect constraints
    for constraint in constraints:
        if isinstance(constraint, ReserveResourceConstraint):
            if constraint.location is None:
                globally_reserved[constraint.resource].append(
                    constraint.reservation)
            else:
                locally_reserved[constraint.location][
                    constraint.resource].append(constraint.reservation)
        elif isinstance(constraint, AlignResourceConstraint):
            alignments[constraint.resource] = constraint.alignment

    # A dictionary {(x, y): [vertex, ...], ...}
    chip_contents = defaultdict(list)
    for vertex, xy in iteritems(placements):
        chip_contents[xy].append(vertex)

    for xy, chip_vertices in iteritems(chip_contents):
        # Index of the next free resource in the current chip
        resource_pointers = {resource: 0
                             for resource in machine.chip_resources}

        for vertex in chip_vertices:
            vertex_allocation = {}

            # Make allocations, advancing resource pointers
            for resource, requirement in iteritems(vertices_resources[vertex]):
                proposed_allocation = None
                proposal_overlaps = True
                while proposal_overlaps:
                    # Check that the proposed allocation doesn't overlap a
                    # reserved area.
                    start = align(resource_pointers[resource],
                                  alignments[resource])
                    proposed_allocation = slice(start, start + requirement)
                    proposal_overlaps = False
                    if proposed_allocation.stop > machine[xy][resource]:
                        raise InsufficientResourceError(
                            "{} over-allocated on chip {}".format(resource,
                                                                  xy))
                    for reservation in globally_reserved[resource]:
                        if slices_overlap(proposed_allocation, reservation):
                            resource_pointers[resource] = reservation.stop
                            proposal_overlaps = True
                    local_reservations \
                        = locally_reserved.get(xy, {}).get(resource, [])
                    for reservation in local_reservations:
                        if slices_overlap(proposed_allocation, reservation):
                            resource_pointers[resource] = reservation.stop
                            proposal_overlaps = True

                # Getting here means the proposed allocation is not blocked
                # by any reservations
                vertex_allocation[resource] = proposed_allocation
                resource_pointers[resource] = proposed_allocation.stop

            allocation[vertex] = vertex_allocation

    return allocation
