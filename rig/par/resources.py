"""Common per-chip resources which may be allocated in a SpiNNaker machine.

These sentinels are simply provided to cover common cases. Users may define
their own application-specific resources as required.
"""

import sentinel

"""Usable application processor cores."""
Cores = sentinel.create("Cores")

"""Shared off-chip SDRAM: bytes."""
SDRAM = sentinel.create("SDRAM")

"""Shared on-chip SRAM: bytes."""
SRAM = sentinel.create("SRAM")
