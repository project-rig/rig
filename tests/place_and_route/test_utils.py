import pytest
import warnings

from rig.place_and_route.utils import \
    build_machine, build_core_constraints, build_application_map, \
    _get_minimal_core_reservations, build_routing_tables

from rig.place_and_route.machine import Machine, Cores

from rig.links import Links

from rig.netlist import Net

from rig.routing_table import Routes, RoutingTableEntry

from rig.place_and_route.routing_tree import RoutingTree

from rig.place_and_route.constraints import ReserveResourceConstraint

from rig.machine_control.machine_controller import SystemInfo, ChipInfo

from rig.machine_control.consts import AppState


def test_build_null_machine():
    # Describe a 1x1 machine with all dead chips...
    system_info = SystemInfo(1, 1, {})

    m = build_machine(system_info)

    assert m.width == 1
    assert m.height == 1
    assert m.dead_chips == set([(0, 0)])


def test_build_machine():
    # Describe a 10x8 machine where everything is nominal except:
    # * (0, 1) is dead
    # * (2, 3) has 17 cores, the rest 18
    # * (4, 5) has no north link, all others have working links
    # * (6, 7) has no SDRAM
    # * (7, 6) has no SRAM
    system_info = SystemInfo(10, 8, {
        (x, y): ChipInfo(
            num_cores=(17 if (x, y) == (2, 3) else 18),
            core_states=[AppState.idle
                         if (x, y, c) != (2, 3, 17) else
                         AppState.dead
                         for c in range(17 if (x, y) == (2, 3) else 18)],
            working_links=(set(l for l in Links if l != Links.north)
                           if (x, y) == (4, 5) else
                           set(Links)),
            largest_free_sdram_block=(0 if (x, y) == (6, 7)
                                      else 10 * 1024 * 1024),
            largest_free_sram_block=(0 if (x, y) == (7, 6)
                                     else 1 * 1024 * 1024),
        )
        for x in range(10)
        for y in range(8)
        if (x, y) != (0, 1)
    })

    m = build_machine(system_info,
                      core_resource="MyCores",
                      sdram_resource="MySDRAM",
                      sram_resource="MySRAM")

    # Check that the machine is correct
    assert isinstance(m, Machine)
    assert m.width == 10
    assert m.height == 8
    assert m.chip_resources == {
        "MyCores": 18,
        "MySDRAM": 10 * 1024 * 1024,
        "MySRAM": 1 * 1024 * 1024,
    }
    assert m.chip_resource_exceptions == {
        (2, 3): {
            "MyCores": 17,
            "MySDRAM": 10 * 1024 * 1024,
            "MySRAM": 1 * 1024 * 1024,
        },
        (6, 7): {
            "MyCores": 18,
            "MySDRAM": 0,
            "MySRAM": 1 * 1024 * 1024,
        },
        (7, 6): {
            "MyCores": 18,
            "MySDRAM": 10 * 1024 * 1024,
            "MySRAM": 0,
        },
    }
    assert m.dead_chips == set([(0, 1)])
    assert m.dead_links == set([(4, 5, Links.north)])


@pytest.mark.parametrize(
    "cores,expected_slices",
    [
        # Special case: No reservations!
        ([], []),
        # Singletons
        ([0], [slice(0, 1)]),
        ([1], [slice(1, 2)]),
        ([17], [slice(17, 18)]),
        # Contiguous ranges
        ([0, 1], [slice(0, 2)]),
        ([3, 4, 5, 6], [slice(3, 7)]),
        # Multiple, disjoint ranges
        ([0, 2, 3], [slice(0, 1), slice(2, 4)]),
        ([0, 1, 16, 17], [slice(0, 2), slice(16, 18)]),
    ])
def test__get_minimal_core_reservations(cores, expected_slices):
    reservations = _get_minimal_core_reservations("MyCores", cores, (1, 2))
    assert [r.reservation for r in reservations] == expected_slices


@pytest.mark.parametrize("global_core_0", [False, True])
def test_build_core_constraints(global_core_0):
    # * A 4x1 machine
    # * (1, 0) has 17 cores, the rest 18
    # * All 18-core chips have a busy core 17
    # * All chips have a cores 0-(x+1) busy if global_core_0 else 1-(x+1)
    system_info = SystemInfo(4, 1, {
        (x, y): ChipInfo(
            num_cores=(17 if (x, y) == (1, 0) else 18),
            core_states=[(AppState.run
                          if ((0 if global_core_0 else 1) <= c <= x
                              or c == 17)
                          else AppState.idle)
                         for c in range(17 if (x, y) == (1, 0) else 18)],
            working_links=set(Links),
            largest_free_sdram_block=100,
            largest_free_sram_block=10,
        )
        for x in range(4)
        for y in range(1)
    })

    constraints = build_core_constraints(system_info, "MyCores")

    # Should end up with:
    # * 1 global constraint (if global_core_0)
    # * 1 constraint on chips x=1 to 3 for the unique reservation
    # * 1 constraint on chips x=0, 2 and 3 to reserve core 18
    assert len(constraints) == (7 if global_core_0 else 6)

    # All constraints must reserve cores
    assert all(isinstance(c, ReserveResourceConstraint)
               for c in constraints)
    assert all(c.resource == "MyCores" for c in constraints)

    # The first constraint must be the global reservation
    if global_core_0:
        global_reservation = constraints.pop(0)
        assert global_reservation.reservation == slice(0, 1)
        assert global_reservation.location is None

    # The remaining constraints should cover those expected above
    # A set of (x, y, start, stop) tuples.
    expected_ranges = set([
        # Core 18 reservations
        (0, 0, 17, 18),
        (2, 0, 17, 18),
        (3, 0, 17, 18),

        # Other reservations
        (1, 0, 1, 2),
        (2, 0, 1, 3),
        (3, 0, 1, 4),
    ])
    for constraint in constraints:
        assert constraint.location is not None
        x, y = constraint.location
        expected_ranges.remove((
            x, y,
            constraint.reservation.start,
            constraint.reservation.stop))
    assert len(expected_ranges) == 0


def test_build_application_map():
    # Test null-case
    assert build_application_map({}, {}, {}) == {}

    # Test with single application on single core
    v = object()
    vertices_applications = {v: "my_app.aplx"}
    placements = {v: (0, 0)}
    allocation = {v: {Cores: slice(1, 2)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1])}}

    # Test with single application on many cores
    v = object()
    vertices_applications = {v: "my_app.aplx"}
    placements = {v: (0, 0)}
    allocation = {v: {Cores: slice(1, 4)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1, 2, 3])}}

    # Test with single application on many chips
    v2 = object()
    v1 = object()
    v0 = object()
    vertices_applications = {v0: "my_app.aplx",
                             v1: "my_app.aplx",
                             v2: "my_app.aplx"}
    placements = {v0: (0, 0), v1: (0, 0), v2: (1, 0)}
    allocation = {v0: {Cores: slice(1, 2)},
                  v1: {Cores: slice(2, 3)},
                  v2: {Cores: slice(1, 2)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1, 2]), (1, 0): set([1])}}

    # Test with multiple applications
    v2 = object()
    v1 = object()
    v0 = object()
    vertices_applications = {v0: "my_app.aplx",
                             v1: "other_app.aplx",
                             v2: "my_app.aplx"}
    placements = {v0: (0, 0), v1: (0, 0), v2: (1, 0)}
    allocation = {v0: {Cores: slice(1, 2)},
                  v1: {Cores: slice(2, 3)},
                  v2: {Cores: slice(1, 2)}}
    assert build_application_map(vertices_applications,
                                 placements, allocation) == \
        {"my_app.aplx": {(0, 0): set([1]), (1, 0): set([1])},
         "other_app.aplx": {(0, 0): set([2])}}


def test_build_routing_tables():
    # Single net with a multi-hop route with a fork in the middle
    net = Net(object(), object())
    r6 = RoutingTree((3, 1), set([(Routes.core_6, net.sinks[0])]))
    r5 = RoutingTree((5, 0), set([(Routes.core_5, net.sinks[0])]))
    r4 = RoutingTree((4, 0), set([(Routes.east, r5)]))
    r3 = RoutingTree((3, 0), set([(Routes.east, r4), (Routes.north, r6)]))
    r2 = RoutingTree((2, 0), set([(Routes.east, r3)]))
    r1 = RoutingTree((1, 0), set([(Routes.east, r2)]))
    r0 = RoutingTree((0, 0), set([(Routes.east, r1)]))
    routes = {net: r0}
    net_keys = {net: (0xDEAD, 0xBEEF)}

    # Build and keep default routes
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        assert build_routing_tables(routes, net_keys, False) == \
            {(0, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF)],
             (1, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                        {Routes.west})],
             (2, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                        {Routes.west})],
             (3, 0): [RoutingTableEntry({Routes.north, Routes.east},
                                        0xDEAD, 0xBEEF, {Routes.west})],
             (4, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF,
                                        {Routes.west})],
             (5, 0): [RoutingTableEntry({Routes.core_5}, 0xDEAD, 0xBEEF,
                                        {Routes.west})],
             (3, 1): [RoutingTableEntry({Routes.core_6}, 0xDEAD, 0xBEEF,
                                        {Routes.south})]}

        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

    # Build and remove default routes
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert build_routing_tables(routes, net_keys) == \
            {(0, 0): [RoutingTableEntry({Routes.east}, 0xDEAD, 0xBEEF)],
             (3, 0): [RoutingTableEntry({Routes.north, Routes.east},
                                        0xDEAD, 0xBEEF, {Routes.west})],
             (5, 0): [RoutingTableEntry({Routes.core_5}, 0xDEAD, 0xBEEF,
                                        {Routes.west})],
             (3, 1): [RoutingTableEntry({Routes.core_6}, 0xDEAD, 0xBEEF,
                                        {Routes.south})]}

        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
