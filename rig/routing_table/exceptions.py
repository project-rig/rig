class MinimisationFailedError(Exception):
    """Raised when a routing table could not be minimised to reach a specified
    target.

    Attributes
    ----------
    target_length : int
        The target number of routing entries.
    final_length : int
        The number of routing entries reached when the algorithm completed.
        (final_length > target_length)
    chip : (x, y) or None
        The coordinates of the chip on which routing table minimisation first
        failed. Only set when minimisation is performed across many chips
        simultaneously.
    """

    def __init__(self, target_length, final_length, chip=None):
        self.chip = chip
        self.target_length = target_length
        self.final_length = final_length

    def __str__(self):
        if self.chip is not None:
            x, y = self.chip
            return ("Could not minimise routing table for ({x}, {y}) to "
                    "fit in {0.target_length} entries. Best managed was "
                    "{0.final_length} entries".format(self, x=x, y=y))
        else:
            return ("Could not minimise routing table to fit in "
                    "{0.target_length} entries, best managed was "
                    "{0.final_length} entries".format(self))
