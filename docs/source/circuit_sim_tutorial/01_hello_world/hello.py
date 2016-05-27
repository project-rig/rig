"""
A Rig-based program which boots a SpiNNaker machine and loads the "hello world"
SpiNNaker binary onto it.
"""

import sys

from rig.machine_control import MachineController

# Control the SpiNNaker machine whose hostname is given on the command line
mc = MachineController(sys.argv[1])

# Boot the machine (if required)
mc.boot()

# Load the hello world application onto core 1 of chip (0, 0).
mc.load_application("hello.aplx", {(0, 0): {1}})

# Wait for the application to finish
mc.wait_for_cores_to_reach_state("exit", 1)

# Print out the message printed by the application
print(mc.get_iobuf(x=0, y=0, p=1))

# Free up any SpiNNaker resources 
mc.send_signal("stop")
