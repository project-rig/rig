import pytest

from six import iteritems

from rig.machine import Machine, Cores, SDRAM
from rig.netlist import Net

from rig.place_and_route import wrapper


class Vertex(object):
    """A generic object which is used as the vertex type in these tests.

    Explicitly meets the requirements of a vertex object according to the
    documentation."""

    def __init__(self):
        pass

    def __eq__(self, other):
        return id(self) == id(other)

    def __hash__(self):
        return hash(id(self))


class TestWrapper(object):
    """Simple santy-check level tests of the wrapper, no comprehensive checks
    since internal function is largely tested elsewhere."""

    def test_empty(self):
        # Simplest possible case of an empty system
        m = Machine(1, 1)
        placements, allocations, application_map, routing_tables = \
            wrapper({}, {}, [], {}, m)
        assert placements == {}
        assert allocations == {}
        assert application_map == {}
        assert routing_tables == {}

    @pytest.mark.parametrize("reserve_monitor, align_sdram",
                             [(True, True), (False, False)])
    def test_ring(self, reserve_monitor, align_sdram):
        # A simple example where a ring network is defined. In the ring, each
        # node is connected by a multicast net to its two immediate neighbours.

        m = Machine(2, 2)

        # Create a ring network which will consume all available cores
        num_vertices = m.width * m.height * (
            m.chip_resources[Cores] - (1 if reserve_monitor else 0))
        vertices = [Vertex() for _ in range(num_vertices)]
        vertices_resources = {v: {Cores: 1, SDRAM: 3} for v in vertices}
        vertices_applications = {v: "app.aplx" for v in vertices}
        nets = [Net(vertices[i],
                    [vertices[(i - 1) % num_vertices],
                     vertices[(i + 1) % num_vertices]])
                for i in range(num_vertices)]
        net_keys = {n: (i, 0xFFFF) for i, n in enumerate(nets)}

        placements, allocations, application_map, routing_tables = \
            wrapper(vertices_resources, vertices_applications,
                    nets, net_keys, m, reserve_monitor=reserve_monitor,
                    align_sdram=align_sdram)

        # Check all vertices are placed & allocated
        assert set(vertices) == set(placements) == set(allocations)

        # Sanity check placement and allocation
        used_cores = set()
        used_memory = set()
        for vertex in vertices:
            x, y = placements[vertex]
            allocation = allocations[vertex]

            # Placed in the machine
            assert (x, y) in m

            # Got one core
            cores = allocation[Cores]
            assert cores.stop - cores.start == 1

            # Not the monitor and within the cores that exist
            if reserve_monitor:
                assert 1 < cores.stop <= m.chip_resources[Cores]
            else:
                assert 0 < cores.stop <= m.chip_resources[Cores]

            # No cores are over-allocated
            assert (x, y, cores.start) not in used_cores
            used_cores.add((x, y, cores.start))

            # Memory got allocated
            sdram = allocation[SDRAM]
            assert sdram.stop - sdram.start == 3

            # Memory was aligned
            if align_sdram:
                assert sdram.start % 4 == 0

            # No memory was over-allocated
            assert (x, y, sdram.start) not in used_memory
            used_memory.add((x, y, sdram.start))

        # Check the correct application map is given (same app on every core)
        assert application_map == {  # pragma: no branch
            "app.aplx": {(x, y): set(range(1 if reserve_monitor else 0,
                                           m.chip_resources[Cores]))
                         for x in range(m.width)
                         for y in range(m.height)}}

        # Check that all routing keys are observed at least once
        used_keys = set()
        for chip, routing_entries in iteritems(routing_tables):
            assert chip in m
            for entry in routing_entries:
                # No routes should terminate on a null
                assert entry.route != set()
                used_keys.add(entry.key)
                assert entry.mask == 0xFFFF
        assert used_keys == set(range(num_vertices))
