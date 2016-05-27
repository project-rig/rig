#!/usr/bin/env python

"""
A library/host-program which uses SpiNNaker to simulate user-defined digital
circuits.
"""

import time
import struct

from bitarray import bitarray

from rig.netlist import Net

from rig.place_and_route import place_and_route_wrapper, Cores, SDRAM

from rig.machine_control import MachineController
from rig.machine_control.utils import sdram_alloc_for_vertices


class _Wire(object):
    """A wire which connects one component's output to many components'
    inputs.
    
    For internal use: to be constructed via :py:meth:`.Simulator._new_wire`
    only.
    """
    
    def __init__(self, source, sinks, routing_key):
        """Defines a new wire from source to sinks which will use the specified
        routing key.
        
        Parameters
        ----------
        source : component
        sinks : [component, ...]
        routing_key : int
        """
        self.source = source
        self.sinks = sinks
        self.routing_key = routing_key


class Gate(object):
    """A 2-input 1-output logic gate implemented using a lookup-table."""
    
    def __init__(self, simulator, lookup_table):
        """Define a new gate.
        
        Parameters
        ----------
        simulator : :py:class:`.Simulator`
            The simulator which will be responsible for simulating this gate.
        lookup_table : int
            A lookup table giving the output value of the gate as a 4-bit
            number where each bit gives the output for a particular combination
            of input values.
            
            =======  =======  ==============
            input a  input b  lut bit number
            =======  =======  ==============
            0        0        0
            1        0        1
            0        1        2
            1        1        3
            =======  =======  ==============
        """
        self._simulator = simulator
        self._lookup_table = lookup_table
        
        # Register this component with the simulator
        self._simulator._add_component(self)
        
        # The two inputs, initially not connected
        self._inputs = {"a": None, "b": None}
        
        # A new wire will be created and sourced by this gate
        self.output = self._simulator._new_wire(self)
    
    def connect_input(self, name, wire):
        """Connect the specified input to a wire."""
        self._inputs[name] = wire
        wire.sinks.append(self)
    
    def _get_kernel(self):
        """Get the filename of the SpiNNaker application kernel to use."""
        return "gate.aplx"
    
    def _get_config_size(self):
        """Get the size of configuration block needed for this gate."""
        # The config contains 5x uint32_t
        return 5 * 4
    
    def _write_config(self, memory):
        """Write the configuration for this gate to memory."""
        memory.seek(0)
        memory.write(struct.pack("<5I",
                                 # sim_length
                                 self._simulator.length,
                                 # input_a_key
                                 self._inputs["a"].routing_key
                                     if self._inputs["a"] is not None
                                     else 0xFFFFFFFF,
                                 # input_b_key
                                 self._inputs["b"].routing_key
                                     if self._inputs["b"] is not None
                                     else 0xFFFFFFFF,
                                 # output_key
                                 self.output.routing_key,
                                 # lut
                                 self._lookup_table))
    
    def _read_results(self, memory):
        """No results to be read!"""
        pass


class And(Gate):
    """An AND gate."""
    
    def __init__(self, simulator):
        super(And, self).__init__(simulator, 0b1000)


class Or(Gate):
    """An OR gate."""
    
    def __init__(self, simulator):
        super(Or, self).__init__(simulator, 0b1110)


class Xor(Gate):
    """An XOR gate."""
    
    def __init__(self, simulator):
        super(Xor, self).__init__(simulator, 0b0110)


class Not(Gate):
    """An NOT gate/inverter.
    
    This internally uses a 2-input gate with the second input never connected.
    """
    
    def __init__(self, simulator):
        super(Not, self).__init__(simulator, 0b0101)
    
    def connect_input(self, wire):
        super(Not, self).connect_input("a", wire)


class Probe(object):
    """A 1-bit recording probe."""
    
    def __init__(self, simulator):
        """Define a new probe.
        
        Parameters
        ----------
        simulator : :py:class:`.Simulator`
            The simulator in which the probe will be used.
        """
        self._simulator = simulator
        self.recorded_data = None
        
        # Register this component with the simulator
        self._simulator._add_component(self)
        
        # The input, initially disconnected
        self._input = None
    
    def connect_input(self, wire):
        """Probe the specified wire."""
        self._input = wire
        wire.sinks.append(self)
    
    def _get_kernel(self):
        """Get the filename of the SpiNNaker application kernel to use."""
        return "probe.aplx"
    
    def _get_config_size(self):
        """Get the size of configuration block needed for this probe."""
        # The config contains 2x uint32_t and a byte for every 8 bits of
        # recorded data.
        return (2 * 4) + ((self._simulator.length + 7) // 8)
    
    def _write_config(self, memory):
        """Write the configuration for this probe to memory."""
        memory.seek(0)
        memory.write(struct.pack("<II",
                                 # sim_length
                                 self._simulator.length,
                                 # input_key
                                 self._input.routing_key
                                     if self._input is not None
                                     else 0xFFFFFFFF))
    
    def _read_results(self, memory):
        """Read back the probed results.
        
        Returns
        -------
        str
            A string of "0"s and "1"s, one for each millisecond of simulation.
        """
        # Seek to the simulation data and read it all back
        memory.seek(8)
        bits = bitarray(endian="little")
        bits.frombytes(memory.read())
        self.recorded_data = bits.to01()


class Stimulus(object):
    """A 1-bit stimulus source."""
    
    def __init__(self, simulator, stimulus=""):
        """Define a new stimulus source.
        
        Parameters
        ----------
        simulator : :py:class:`.Simulator`
            The simulator in which the stimulus will be used.
        stimulus : str
            A string of "0" and "1"s giving the stimulus to generate for each
            millisecond in the simulation. Will be zero-padded or truncated to
            match the length of the simulation.
        """
        self._simulator = simulator
        self.stimulus = stimulus
        
        # Register this component with the simulator
        self._simulator._add_component(self)
        
        # A new wire will be created sourced by this stimulus generator
        self.output = self._simulator._new_wire(self)
    
    def _get_kernel(self):
        """Get the filename of the SpiNNaker application kernel to use."""
        return "stimulus.aplx"
    
    def _get_config_size(self):
        """Get the size of configuration block needed for this stimulus."""
        # The config contains 2x uint32_t and a byte for every 8 bits of
        # stimulus data.
        return (2 * 4) + ((self._simulator.length + 7) // 8)
    
    def _write_config(self, memory):
        """Write the configuration for this stimulus to memory."""
        memory.seek(0)
        memory.write(struct.pack("<II",
                                 # sim_length
                                 self._simulator.length,
                                 # output_key
                                 self.output.routing_key))
        
        # NB: memory.write will automatically truncate any excess stimulus
        memory.write(bitarray(
            self.stimulus.ljust(self._simulator.length, "0"),
            endian="little").tobytes())
    
    def _read_results(self, memory):
        """No results to be read!"""
        pass


class Simulator(object):
    """A SpiNNaker-based digital logic simulator."""
    
    def __init__(self, hostname, length):
        """Create a new simulation.
        
        Parameters
        ----------
        hostname : str
            The hostname or IP of the SpiNNaker machine to use.
        length : int
            The number of milliseconds to run the simulation for.
        """
        self._hostname = hostname
        self.length = length
        
        # A list of components added to the simulation
        self._components = []
        
        # A list of wires used in the simulation
        self._wires = []
    
    def _add_component(self, component):
        """Add a component to the simulation.
        
        Called internally by components on construction.
        """
        self._components.append(component)
    
    def _new_wire(self, source, sinks=[]):
        """Create a new :py:class:`._Wire` with a unique routing key."""
        # Assign sequential routing key to new nets.
        wire = _Wire(source, sinks, len(self._wires))
        self._wires.append(wire)
        
        return wire
    
    def run(self):
        """Run the simulation."""
        # Define the resource requirements of each component in the simulation.
        vertices_resources = {
            # Every component runs on exactly one core and consumes a certain
            # amount of SDRAM to hold configuration data.
            component: {Cores: 1, SDRAM: component._get_config_size()}
            for component in self._components
        }
        
        # Work out what SpiNNaker application needs to be loaded for each
        # component
        vertices_applications = {component: component._get_kernel()
                                 for component in self._components}
        
        # Convert the Wire objects into Rig Net objects and create a lookup
        # from Net to the (key, mask) to use.
        net_keys = {Net(wire.source, wire.sinks): (wire.routing_key, 0xFFFFFFFF)
                    for wire in self._wires}
        nets = list(net_keys)
        
        # Boot the SpiNNaker machine and interrogate it to determine what
        # resources (e.g. cores, SDRAM etc.) are available.
        mc = MachineController(self._hostname)
        mc.boot()
        system_info = mc.get_system_info()
        
        
        # Automatically chose which chips and cores to use for each component
        # and generate routing tables.
        placements, allocations, application_map, routing_tables = \
            place_and_route_wrapper(vertices_resources,
                                    vertices_applications,
                                    nets, net_keys,
                                    system_info)
        
        with mc.application():
            # Allocate memory for configuration data, tagged by core number.
            memory_allocations = sdram_alloc_for_vertices(mc, placements,
                                                          allocations)
            
            # Load the configuration data for all components
            for component, memory in memory_allocations.items():
                component._write_config(memory)
            
            # Load all routing tables
            mc.load_routing_tables(routing_tables)
            
            # Load all SpiNNaker application kernels
            mc.load_application(application_map)
            
            # Wait for all six cores to reach the 'sync0' barrier
            mc.wait_for_cores_to_reach_state("sync0", len(self._components))
            
            # Send the 'sync0' signal to start execution and wait for the
            # simulation to finish.
            mc.send_signal("sync0")
            time.sleep(self.length * 0.001)
            mc.wait_for_cores_to_reach_state("exit", len(self._components))
            
            # Retrieve result data
            for component, memory in memory_allocations.items():
                component._read_results(memory)
