"""Docstring sanitisers for Sphinx"""


def int_enum_doc(enum):
    """Decorator which re-writes documentation strings for an IntEnum so that
    Sphinx presents it correctly.

    This is a work-around for Sphinx autodoc's inability to properly document
    IntEnums.
    """
    enum.__doc__ += "\n\nAttributes\n==========\n"
    for val in list(enum):
        enum.__doc__ += "{} = {}\n".format(val.name, int(val))

    return enum
