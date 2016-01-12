from rig.routing_table import MinimisationFailedError


def test_minimisation_failed_error_str():
    # With no chip and no achieved length
    assert (
        str(MinimisationFailedError(10)) ==
        "Could not minimise routing table to fit in 10 entries."
    )

    # With no chip and achieved length
    assert (
        str(MinimisationFailedError(10, 5)) ==
        "Could not minimise routing table to fit in 10 entries. " +
        "Best managed was 5 entries."
    )

    # With chip and no achieved length
    assert (
        str(MinimisationFailedError(10, chip=(3, 4))) ==
        "Could not minimise routing table for (3, 4) to fit in 10 entries."
    )

    # With chip and no achieved length
    assert (
        str(MinimisationFailedError(10, 2, (3, 4))) ==
        "Could not minimise routing table for (3, 4) to fit in 10 entries. "
        "Best managed was 2 entries."
    )
