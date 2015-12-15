"""**Deprecated.** Contains aliases for backward compatibility which should not
be used in new code.
"""

import warnings

from rig.links import Links  # noqa

from rig.place_and_route import Machine, Cores, SDRAM, SRAM  # noqa


warnings.warn(
    "The contents of the rig.machine module have been moved to better reflect "
    "their purpose. The Machine object and Cores, SDRAM and SRAM sentinels "
    "have moved to rig.place_and_route. The Links datastructure has moved to "
    "rig.links.", DeprecationWarning)
