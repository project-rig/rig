"""
A Rig-based program which loads a pair of 32-bit integers into SpiNNaker's
SDRAM which are then summed by a SpiNNaker application kernel.
"""

import sys
import random
import struct

from rig.machine_control import MachineController

# Control the SpiNNaker machine whose hostname is given on the command line.
mc = MachineController(sys.argv[1])

# Boot the machine (if required)
mc.boot()

# Allocate space for the two 32-bit numbers to add together and the 32-bit
# result.
sdram_addr = mc.sdram_alloc(12, x=0, y=0, tag=1)

# Pick two random numbers to be added together and write them to SDRAM
num_a = random.getrandbits(30)
num_b = random.getrandbits(30)
data = struct.pack("<II", num_a, num_b)
mc.write(sdram_addr, data, x=0, y=0)

# Load the adder application onto core 1 of chip (0, 0).
mc.load_application("adder.aplx", {(0, 0): {1}})

# Wait for the application to finish
mc.wait_for_cores_to_reach_state("exit", 1)

# Read back the result and print it out
result_data = mc.read(sdram_addr + 8, 4, x=0, y=0)
result, = struct.unpack("<I", result_data)
print("{} + {} = {}".format(num_a, num_b, result))

# Free up any SpiNNaker resources
mc.send_signal("stop")
