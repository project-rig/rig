#!/usr/bin/env python

"""
An example experiment using the circuit simulator API.
"""

import sys

from circuit_simulator import Simulator, Stimulus, Or, And, Probe

# Define a 64 ms simulation to be run on the given SpiNNaker machine
sim = Simulator(sys.argv[1], 64)

# Define three stimulus generators which together produce all 8 combinations of
# values.
stimulus_a = Stimulus(
    sim, "0000000011111111000000001111111100000000111111110000000011111111")
stimulus_b = Stimulus(
    sim, "0000000000000000111111111111111100000000000000001111111111111111")
stimulus_c = Stimulus(
    sim, "0000000000000000000000000000000011111111111111111111111111111111")

# Define the two gates
or_gate = Or(sim)
and_gate = And(sim)

# Define a probe to record the output of the circuit
probe = Probe(sim)

# Wire everything together
or_gate.connect_input("a", stimulus_a.output)
or_gate.connect_input("b", stimulus_b.output)

and_gate.connect_input("a", stimulus_c.output)
and_gate.connect_input("b", or_gate.output)

probe.connect_input(and_gate.output)

# Run the simulation
sim.run()

# Print the results
print("Stimulus A: " + stimulus_a.stimulus)
print("Stimulus B: " + stimulus_b.stimulus)
print("Stimulus C: " + stimulus_c.stimulus)
print("Probe:      " + probe.recorded_data)
