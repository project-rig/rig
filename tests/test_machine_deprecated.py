import warnings


def test_deprecated():
    with warnings.catch_warnings(record=True) as w:
        warnings.filterwarnings("always", module="rig[.]machine")

        from rig.machine import Machine, Cores, SDRAM, SRAM, Links

        # Should be flagged as deprecated
        print(w)
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

    # Aliases should be correct
    from rig import place_and_route, links
    assert Machine is place_and_route.Machine
    assert Cores is place_and_route.Cores
    assert SDRAM is place_and_route.SDRAM
    assert SRAM is place_and_route.SRAM
    assert Links is links.Links
