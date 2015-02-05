"""Exceptions which placers can throw to indicate standard types of problem.
"""


class InsufficientResourceError(Exception):
    """Indication that a process failed because adequate resources were not
    available in the machine.
    """
    pass


class InvalidConstraintError(Exception):
    """Indication that a process failed because an impossible constraint was
    given.
    """
    pass
