"""A collection of utilities for mapping a hyper-graph (vertices and nets) to a
SpiNNaker machine.

Users are referred to the documentation for an specification/introduction to
the use of these functions.
"""

# Default algorithms
from .place.sa import place
from .allocate.greedy import allocate
from .route.ner import route

# High-Level Wrapper
from .wrapper import place_and_route_wrapper
from .wrapper import wrapper  # Deprecated

# Machine datastructure
from .machine import Machine, Cores, SDRAM, SRAM
