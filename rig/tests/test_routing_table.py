import pytest

from rig.machine import Links

from rig.routing_table import Routes


def test_routes():
    # Make sure Links are cast correctly
    assert Routes.east is Routes(Links.east)
    assert Routes.north_east is Routes(Links.north_east)
    assert Routes.north is Routes(Links.north)
    assert Routes.west is Routes(Links.west)
    assert Routes.south_west is Routes(Links.south_west)
    assert Routes.south is Routes(Links.south)

    # Make sure core lookup works correctly
    assert Routes.core(0) is Routes.core_monitor
    assert Routes.core(1) is Routes.core_1
    assert Routes.core(2) is Routes.core_2
    assert Routes.core(3) is Routes.core_3
    assert Routes.core(4) is Routes.core_4
    assert Routes.core(5) is Routes.core_5
    assert Routes.core(6) is Routes.core_6
    assert Routes.core(7) is Routes.core_7
    assert Routes.core(8) is Routes.core_8
    assert Routes.core(9) is Routes.core_9
    assert Routes.core(10) is Routes.core_10
    assert Routes.core(11) is Routes.core_11
    assert Routes.core(12) is Routes.core_12
    assert Routes.core(13) is Routes.core_13
    assert Routes.core(14) is Routes.core_14
    assert Routes.core(15) is Routes.core_15
    assert Routes.core(16) is Routes.core_16
    assert Routes.core(17) is Routes.core_17

    # Lookups out of range should fail
    with pytest.raises(Exception):
        Routes.core(-1)
    with pytest.raises(Exception):
        Routes.core(18)
