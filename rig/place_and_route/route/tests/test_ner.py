import pytest

from collections import deque

from rig.machine import Machine, Links

from rig.place_and_route.routing_tree import RoutingTree

from rig.place_and_route.route.utils import links_between

from rig.place_and_route.route.ner import ner_net, \
    copy_and_disconnect_tree, a_star, avoid_dead_links

from rig.place_and_route.exceptions import MachineHasDisconnectedSubregion


def test_ner_net_childless():
    # "Exhaustive" test for childless special cases

    # Childless net: results should just contain the source node
    root, lookup = ner_net((0, 0), [], 1, 1)
    assert root.chip == (0, 0)
    assert root.children == set()
    assert lookup[(0, 0)] is root
    assert len(lookup) == 1

    # Childless net at non-zero coordinate
    root, lookup = ner_net((0, 1), [], 2, 2)
    assert root.chip == (0, 1)
    assert root.children == set()
    assert lookup[(0, 1)] is root
    assert len(lookup) == 1


# Test cases for test_ner_net.
# [ (source, [destination, ...], width, height, wrap_around, radius), ...]
ner_net_testcases = [
    # Childless cases (sanity checks the test: these should pass iff
    # test_ner_net_childless passes).
    ((0, 0), [], 1, 1, True, 20),
    ((0, 1), [], 2, 2, True, 20),

    # Single children in adjacent locations
    ((1, 1), [(2, 1)], 3, 3, True, 20), ((1, 1), [(2, 1)], 3, 3, False, 20),
    ((1, 1), [(0, 1)], 3, 3, True, 20), ((1, 1), [(0, 1)], 3, 3, False, 20),
    ((1, 1), [(1, 2)], 3, 3, True, 20), ((1, 1), [(1, 2)], 3, 3, False, 20),
    ((1, 1), [(1, 0)], 3, 3, True, 20), ((1, 1), [(1, 0)], 3, 3, False, 20),
    ((1, 1), [(2, 2)], 3, 3, True, 20), ((1, 1), [(2, 2)], 3, 3, False, 20),
    ((1, 1), [(0, 0)], 3, 3, True, 20), ((1, 1), [(0, 0)], 3, 3, False, 20),

    # Single children in non-adjacent locations, potentially wrapping and
    # non-wrapping
    ((0, 0), [(9, 0)], 10, 10, True, 20),
    ((0, 0), [(9, 0)], 10, 10, False, 20),
    ((0, 0), [(0, 9)], 10, 10, True, 20),
    ((0, 0), [(0, 9)], 10, 10, False, 20),
    ((0, 0), [(9, 9)], 10, 10, True, 20),
    ((0, 0), [(9, 9)], 10, 10, False, 20),

    # Multiple children in a line (wrapping and not-wrapping)
    ((0, 0), [(1, 0), (2, 0)], 3, 3, True, 20),
    ((0, 0), [(1, 0), (2, 0)], 3, 3, False, 20),
    ((0, 0), [(0, 1), (0, 2)], 3, 3, True, 20),
    ((0, 0), [(0, 1), (0, 2)], 3, 3, False, 20),
    ((0, 0), [(1, 1), (2, 2)], 3, 3, True, 20),
    ((0, 0), [(1, 1), (2, 2)], 3, 3, False, 20),

    # Distributed selection of destinations (all odd locations)
    ((0, 0),
     [(x, y) for x in range(9) for y in range(9) if x % 2 == 1 and y % 2 == 1],
     9, 9, True, 20),
    ((0, 0),
     [(x, y) for x in range(9) for y in range(9) if x % 2 == 1 and y % 2 == 1],
     9, 9, False, 20),

    # Broadcast to all locations
    ((0, 0),
     [(x, y) for x in range(9) for y in range(9) if (x, y) != (0, 0)],
     9, 9, True, 20),
    ((0, 0),
     [(x, y) for x in range(9) for y in range(9) if (x, y) != (0, 0)],
     9, 9, False, 20),

    # Destination outside radius of source
    ((0, 0), [(8, 8)], 9, 9, False, 3),
    ((0, 0), [(5, 5)], 9, 9, True, 3),

    # Give two pairs of destinations which are within the radius of eachother
    # but not of the other pair or source.
    ((0, 0), [(10, 10), (11, 11), (30, 30), (31, 31)], 100, 100, False, 1),
    ((0, 0), [(10, 10), (11, 11), (30, 30), (29, 29)], 40, 40, True, 1),
]


def test_ner_net():
    # This test checks:
    # * Completeness of connectivity
    # * Tree structure (no loops)
    # * Lack of uneccessary paths
    # * Correctness of lookup

    for (source, destinations, width, height,
         wrap_around, radius) in ner_net_testcases:
        root, lookup = ner_net(source, destinations, width, height,
                               wrap_around, radius)

        # Check all endpoints are in the lookup
        assert source in lookup
        for destination in destinations:
            assert destination in lookup

        # Check that the root in the lookup is consistent
        assert lookup[source] is root

        # Perform a tree-search to check for correctness of the tree

        # (x, y) which have been visited in the search
        visited = set()

        # A stack or queue of ((x, y), node) pairs yet to visit.
        to_visit = deque([(source, root)])
        while to_visit:
            (x, y), node = to_visit.popleft()

            # Check coordinates are correct
            assert (x, y) == node.chip

            # Check for loops
            assert (x, y) not in visited, "Loop detected"
            visited.add((x, y))

            # Ensure that node can be looked up if it is a source/destination
            if (x, y) == source or (x, y) in destinations:
                assert (x, y) in lookup
                assert lookup[(x, y)] is node

            if len(node.children) == 0:
                # Only destinations/sources are allowed to have no children
                # (i.e.  no path should terminate in the middle of nowhere!)
                assert (x, y) == source or (x, y) in destinations
            else:
                for child in node.children:
                    # Check children are actually physically adjacent
                    dx = node.chip[0] - child.chip[0]
                    dy = node.chip[1] - child.chip[1]
                    if wrap_around:
                        assert (dx, dy) in set([(1, 0), (-1, 0),
                                                (0, 1), (0, -1),
                                                (1, 1), (-1, -1),
                                                (width - 1, 0),
                                                (-(width - 1), 0),
                                                (0, height - 1),
                                                (0, -(height - 1)),
                                                (width - 1, height - 1),
                                                (-(width - 1), -(height - 1)),
                                                ])
                    else:
                        assert (dx, dy) in set([(1, 0), (-1, 0),
                                                (0, 1), (0, -1),
                                                (1, 1), (-1, -1)])

                    # Continue the traversal
                    to_visit.append((child.chip, child))

        # Check all sources/destinations were visited
        assert source in visited
        for destination in destinations:
            assert destination in visited


def test_copy_and_disconnect_tree():
    working_machine = Machine(10, 10)
    dead_link_machine = Machine(10, 10, dead_links=set([(0, 0, Links.north)]))
    dead_chip_machine = Machine(10, 10, dead_chips=set([(1, 1)]))

    # Test various trees get copied correctly. A list of test cases (root,
    # machine, broken_links) where `root` is the root of the input tree and
    # `broken_links` is a set([(parent, child), ...]) where `parent` and
    # `child` are (x, y) coordinates of nodes which are disconnected.
    test_cases = []

    # Singleton
    test_cases.append((RoutingTree((0, 0)), working_machine, set()))

    # Tree with nothing broken
    t11 = RoutingTree((1, 2))
    t10 = RoutingTree((0, 2))
    t1 = RoutingTree((0, 1), set([t10, t11]))
    t01 = RoutingTree((2, 0))
    t00 = RoutingTree((2, 1))
    t0 = RoutingTree((1, 0), set([t00, t01]))
    t = RoutingTree((0, 0), set([t0, t1]))
    test_cases.append((t0, working_machine, set()))

    # Tree with broken link
    test_cases.append((t, dead_link_machine, set([((0, 0), (0, 1))])))

    # Tree with a broken chip
    t3 = RoutingTree((1, 2))
    t2 = RoutingTree((2, 1))
    t1 = RoutingTree((1, 1), set([t2, t3]))
    t0 = RoutingTree((0, 0), set([t1]))
    test_cases.append((t0, dead_chip_machine,
                       set([((0, 0), (2, 1)), ((0, 0), (1, 2))])))

    # Run through each test case
    for old_root, machine, expected_broken_links in test_cases:
        old_lookup = dict((node.chip, node) for node in old_root)

        new_root, new_lookup, new_broken_links \
            = copy_and_disconnect_tree(old_root, machine)

        # Make sure root is a copy and has the right coordinates (children will
        # be checked later)
        assert new_root is not old_root
        assert new_root.chip == old_root.chip

        old_chips = set(old_lookup)
        new_chips = set(new_lookup)

        # Check that no new locations have been introduced
        assert old_chips.issuperset(new_chips)

        # Check the locations missing are exactly those on dead cores
        assert (old_chips.difference(new_chips) ==  # pragma: no branch
                set(c for c in old_chips if c not in machine))

        # Check that the set of broken links is as expected
        assert new_broken_links == expected_broken_links

        # Set of chips for which we've seen the parent, intially just the root
        # (which doesn't really have a parent).
        nodes_with_parents = set([new_root.chip])

        # Check each node individually for copy correctness
        for chip in old_lookup:
            old_node = old_lookup[chip]

            # Skip nodes which were on broken chips and thus don't have a new
            # node
            if old_node.chip not in machine:
                continue

            new_node = new_lookup[chip]

            # Make sure it is a copy
            assert old_node is not new_node

            # Make sure the coordinate is correct
            assert chip == old_node.chip == new_node.chip

            for child in new_node.children:
                # Ensure all children are not members of the old tree
                assert old_lookup[child.chip] is not child

                # Ensure they are members of the new tree
                assert new_lookup[child.chip] is child

                # Ensure none of them are children of another node
                assert child not in nodes_with_parents
                nodes_with_parents.add(child)

            old_children = set(c.chip for c in old_node.children)
            new_children = set(c.chip for c in new_node.children)

            # Make sure no children at new positions have been added
            assert old_children.issuperset(new_children)

            # Ensure that any children missing are exactly those which are
            # disconnected or on dead chips
            assert (  # pragma: no branch
                old_children.difference(new_children) ==
                set(c for c in old_children
                    if c not in machine or
                    not links_between(chip, c, machine)))


def test_a_star():
    # This test ensures the sun is currently shining. Honest.
    working_machine = Machine(10, 10)
    dead_link_machine = Machine(10, 10, dead_links=set([(0, 0, Links.north)]))

    # [(sink, heuristic_source, sources), ...]
    test_cases = [
        # Single pair of adjacent nodes
        ((1, 0), (0, 0), set([(0, 0)])),

        # Non-adjacent nodes (potentially wrapping)
        ((2, 0), (0, 0), set([(0, 0)])),
        ((9, 9), (0, 0), set([(0, 0)])),

        # Non-adjacent nodes whose optimal path is sperated by a dead link
        ((0, 2), (0, 0), set([(0, 0)])),

        # Multiple sources with the heuristic source being immediately behind
        # other targets.
        ((0, 3), (0, 0), set([(0, 2), (0, 1), (0, 0)])),

        # Multiple sources with the heuristic source being immediately in-front
        # of other targets.
        ((0, 3), (0, 2), set([(0, 2), (0, 1), (0, 0)])),

        # Multiple sources with the heuristic source being far from other,
        # nearer sources
        ((0, 0), (4, 4), set([(4, 4), (0, 1), (0, 2)])),

        # Multiple sources with the heuristic source being far from other,
        # distant sources
        ((0, 0), (0, 1), set([(4, 4), (5, 5), (0, 1)])),
    ]

    for machine in [working_machine, dead_link_machine]:
        for wrap_around in [True, False]:
            for sink, heuristic_source, sources in test_cases:
                path = a_star(sink, heuristic_source, sources,
                              machine, wrap_around)

                # Path should start at one of the sources
                assert path[0] in sources

                # Path should touch exactly one source
                assert len(set(path).intersection(sources)) == 1

                # Should be a continuous, connected path ending at the sink
                last_step = path[0]
                for step in path[1:] + [sink]:
                    assert links_between(last_step, step, machine)
                    last_step = step

                # Path should not be cyclcic or include the sink
                visited = set([sink])
                for step in path:
                    assert step not in visited
                    visited.add(step)


def test_a_star_impossible():
    # Test a_star fails when presented by a disconnected area of the machine.

    # A machine where the only working link is that going west from (1, 0) to
    # (0, 0).
    machine = Machine(2, 1, dead_links=set((x, 0, l)
                                           for l in Links for x in range(2)
                                           if not (x == 1 and
                                                   l == Links.west)))

    # Ensure we can't get a route out of (0, 0) to (1, 0) since all links
    # leaving it are dead
    with pytest.raises(MachineHasDisconnectedSubregion):
        a_star((1, 0), (0, 0), set([(0, 0)]), machine, True)

    # Ensure, conversely, we can get a route from (1, 0) to (0, 0) thus showing
    # we're obeying link liveness in the correct direction.
    assert a_star((0, 0), (1, 0), set([(1, 0)]), machine, True) == [(1, 0)]


def test_avoid_dead_links_no_change():
    # Ensure this function makes no chaanges when no changes are needed
    machine = Machine(10, 10,
                      dead_links=set([(0, 0, Links.west)]),
                      dead_chips=set([(1, 1)]))

    # [root, ...]
    test_cases = []

    # Singleton
    test_cases.append(RoutingTree((0, 0)))

    # A routing tree which goes near (but avoids) the dead chip and link
    t002 = RoutingTree((1, 3), set([]))
    t001 = RoutingTree((0, 3), set([]))
    t000 = RoutingTree((1, 2), set([]))
    t00 = RoutingTree((0, 2), set([t000, t001, t002]))
    t0 = RoutingTree((0, 1), set([t00]))
    t = RoutingTree((0, 0), set([t0]))
    test_cases.append(t)

    for old_root in test_cases:
        new_root, new_lookup = avoid_dead_links(old_root, machine)

        # Root should be the same
        assert new_root.chip == old_root.chip

        # New lookup should be unchanged
        assert set(new_lookup) == set(r.chip for r in old_root)

        # New lookup should be consistent
        for node in new_root:
            assert new_lookup[node.chip] is node

        for old_node in old_root:
            new_node = new_lookup[old_node.chip]

            # Locations should be the same
            assert new_node.chip == old_node.chip

            # Children should be the same
            assert (  # pragma: no branch
                set(n.chip for n in new_node.children) ==
                set(n.chip for n in old_node.children))


def test_avoid_dead_links_change():
    # Check that when changes are made, the result is a fully connected tree
    machine = Machine(10, 10,
                      # An example dead link
                      dead_links=set([(4, 4, Links.north)]),
                      # A right-angle wall of dead chips just above-right of
                      # (0, 0)
                      dead_chips=set([(1, 1), (2, 1), (3, 1), (4, 1),
                                      (1, 2), (1, 3), (1, 4)]))

    # [root, ...]
    test_cases = []

    # A routing tree which crosses a dead link
    t1 = RoutingTree((4, 5))
    t0 = RoutingTree((4, 4), set([t1]))
    test_cases.append(t0)

    # A routing tree which is blocked by a dead chip
    t2 = RoutingTree((4, 2))
    t1 = RoutingTree((4, 1), set([t2]))
    t0 = RoutingTree((4, 0), set([t1]))
    test_cases.append(t0)

    # A subtree tree which is blocked by a wall of chips
    t002 = RoutingTree((3, 3))
    t001 = RoutingTree((2, 3))
    t000 = RoutingTree((3, 2))
    t00 = RoutingTree((2, 2), set([t000, t001, t002]))
    t0 = RoutingTree((1, 1), set([t00]))
    t = RoutingTree((0, 0), set([t0]))
    test_cases.append(t)

    # A subtree which blocks A* from reaching the start without crossing itself
    # but which doesn't directly encircle the top of the blockage.
    t55 = RoutingTree((2, 5), set([]))
    t54 = RoutingTree((3, 5), set([t55]))
    t53 = RoutingTree((4, 5), set([t54]))
    t52 = RoutingTree((5, 2), set([]))
    t51 = RoutingTree((5, 3), set([t52]))
    t50 = RoutingTree((5, 4), set([t51]))
    t4 = RoutingTree((5, 5), set([t50, t53]))
    t3 = RoutingTree((4, 4), set([t4]))
    t2 = RoutingTree((3, 3), set([t3]))
    t1 = RoutingTree((2, 2), set([t2]))
    t0 = RoutingTree((1, 1), set([t1]))
    t = RoutingTree((0, 0), set([t0]))
    test_cases.append(t)

    # For each test case just ensure the new tree is a tree and visits all
    # non-dead nodes from the testcase. No checks made for
    # minimality/efficiency etc.
    for old_root in test_cases:
        new_root, new_lookup = avoid_dead_links(old_root, machine)

        # Root should be the same
        assert new_root.chip == old_root.chip

        # New lookup should be consistent
        for node in new_root:
            assert new_lookup[node.chip] is node

        # Check all non-dead nodes still exist
        assert (  # pragma: no branch
            set(n.chip for n in old_root if n.chip in machine).issubset(
                set(n.chip for n in new_root)))

        # Check for cycles
        visited = set()
        to_visit = deque([new_root])
        while to_visit:
            node = to_visit.popleft()

            # No loops should exist
            assert node not in visited
            visited.add(node)

            # Node should be in lookup (already know it is consistent if it is)
            assert node.chip in new_lookup

            for child in node.children:
                # All children should be accessible
                assert links_between(node.chip, child.chip, machine)

                # Check children
                to_visit.append(child)
