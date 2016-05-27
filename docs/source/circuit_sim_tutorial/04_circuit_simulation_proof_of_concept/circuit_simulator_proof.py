#!/usr/bin/env python

"""
A proof-of-concept host-program which uses SpiNNaker to simulate a simple
digital circuit.

See part 04 of the Rig tutorial for a description of this circuit.
"""

import sys
import time
import struct

from bitarray import bitarray

from rig.machine_control import MachineController
from rig.routing_table import RoutingTableEntry, Routes

# Use the SpiNNaker machine provided on the command-line
mc = MachineController(sys.argv[1])

# Boot the machine (if required)
mc.boot()

with mc.application():
    # Allocate a tagged block of SDRAM to hold the configuration struct for
    # each application kernel.
    with mc(x=0, y=0):
        # Space for sim_length, output_key and space for 64 ms of stimulus
        # data.
        stimulus_a_config = mc.sdram_alloc_as_filelike(4 + 4 + 8, tag=1)
        stimulus_b_config = mc.sdram_alloc_as_filelike(4 + 4 + 8, tag=2)
        stimulus_c_config = mc.sdram_alloc_as_filelike(4 + 4 + 8, tag=3)
    
    with mc(x=1, y=0):
        # Space for all 5 uint32_t values in the config struct
        or_gate_config = mc.sdram_alloc_as_filelike(5 * 4, tag=1)
        and_gate_config = mc.sdram_alloc_as_filelike(5 * 4, tag=2)
    
    # Space for sim_length, input_key and space for 64 ms of stimulus data.
    probe_config = mc.sdram_alloc_as_filelike(4 + 4 + 8, x=1, y=1, tag=1)
    
    # The stimulus data (tries every combination of a, b and c for 8 ms each)
    #         |       |       |       |       |       |       |       |       |
    stim_a = "0000000011111111000000001111111100000000111111110000000011111111"
    stim_b = "0000000000000000111111111111111100000000000000001111111111111111"
    stim_c = "0000000000000000000000000000000011111111111111111111111111111111"
    
    # Write stimulus configuration structs
    stimulus_a_config.write(struct.pack("<II", 64, 0x00000001))
    stimulus_a_config.write(bitarray(stim_a, endian="little").tobytes())
    
    stimulus_b_config.write(struct.pack("<II", 64, 0x00000002))
    stimulus_b_config.write(bitarray(stim_b, endian="little").tobytes())
    
    stimulus_c_config.write(struct.pack("<II", 64, 0x00000003))
    stimulus_c_config.write(bitarray(stim_c, endian="little").tobytes())
    
    # Write gate configuration structs, setting the look-up-tables to implement
    # the two gates' respective functions.
    or_gate_config.write(struct.pack("<5I",
                                     64,          # sim_length
                                     0x00000001,  # input_a_key
                                     0x00000002,  # input_b_key
                                     0x00000004,  # output_key
                                     0b1110))     # lut (OR)
    and_gate_config.write(struct.pack("<5I",
                                      64,          # sim_length
                                      0x00000004,  # input_a_key
                                      0x00000003,  # input_b_key
                                      0x00000005,  # output_key
                                      0b1000))     # lut (AND)
    
    # Write the probe's configuration struct (note this doesn't write to the
    # buffer used to store recorded values).
    probe_config.write(struct.pack("<II", 64, 0x00000005))
    
    # Define routing tables for each chip
    routing_tables = {(0, 0): [],
                      (1, 0): [],
                      (1, 1): []}
    
    # Wire 1
    routing_tables[(0, 0)].append(
        RoutingTableEntry({Routes.east}, 0x00000001, 0xFFFFFFFF))
    routing_tables[(1, 0)].append(
        RoutingTableEntry({Routes.core_1}, 0x00000001, 0xFFFFFFFF))
    
    # Wire 2
    routing_tables[(0, 0)].append(
        RoutingTableEntry({Routes.east}, 0x00000002, 0xFFFFFFFF))
    routing_tables[(1, 0)].append(
        RoutingTableEntry({Routes.core_1}, 0x00000002, 0xFFFFFFFF))
    
    # Wire 3
    routing_tables[(0, 0)].append(
        RoutingTableEntry({Routes.east}, 0x00000003, 0xFFFFFFFF))
    routing_tables[(1, 0)].append(
        RoutingTableEntry({Routes.core_2}, 0x00000003, 0xFFFFFFFF))
    
    # Wire 4
    routing_tables[(1, 0)].append(
        RoutingTableEntry({Routes.core_2}, 0x00000004, 0xFFFFFFFF))
    
    # Wire 5
    routing_tables[(1, 0)].append(
        RoutingTableEntry({Routes.north}, 0x00000005, 0xFFFFFFFF))
    routing_tables[(1, 1)].append(
        RoutingTableEntry({Routes.core_1}, 0x00000005, 0xFFFFFFFF))
    
    # Allocate and load the above routing entries onto their respective chips
    mc.load_routing_tables(routing_tables)
    
    # Load the application kernels onto the machine
    mc.load_application({
        "stimulus.aplx": {(0, 0): {1, 2, 3}},
        "gate.aplx": {(1, 0): {1, 2}},
        "probe.aplx": {(1, 1): {1}},
    })
    
    # Wait for all six cores to reach the 'sync0' barrier (i.e. call
    # `spin1_start()`).
    mc.wait_for_cores_to_reach_state("sync0", 6)
    
    # Send the 'sync0' signal to start execution and wait for the simulation to
    # finish.
    mc.send_signal("sync0")
    time.sleep(0.064)  # 64 ms
    mc.wait_for_cores_to_reach_state("exit", 6)
    
    # Retrieve the values recorded by the probe
    probe_recording = bitarray(endian="little")
    probe_recording.frombytes(probe_config.read(8))
    
    # Plot the recorded values using pyplot
    import matplotlib.pyplot as plt
    import numpy as np
    time = list(range(64))
    
    # The three input stimuli
    plt.step(time, np.array(bitarray(stim_a)) + 0.0, label="stimulus_a")
    plt.step(time, np.array(bitarray(stim_b)) + 1.5, label="stimulus_b")
    plt.step(time, np.array(bitarray(stim_c)) + 3.0, label="stimulus_c")
    
    # The recorded output
    plt.step(time, np.array(probe_recording) + 6.0, label="probe")
    
    # Format the plot nicely
    plt.margins(y=0.5)
    plt.legend(loc='upper center', ncol=4)
    plt.xlabel("Time (ms)")
    plt.tick_params(axis='y', which='both',
                    left='off', right='off', labelleft='off')
    plt.show()
