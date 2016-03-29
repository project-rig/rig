"""A minimal command-line utility which prints basic information about a
SpiNNaker machine or BMP.

Installed as "rig-info" by setuptools.
"""

import sys
import argparse
from six import iteritems, itervalues
from collections import defaultdict

from datetime import datetime
from pytz import utc

import rig

from rig.place_and_route.utils import build_machine

from rig.machine_control import MachineController, BMPController

from rig.machine_control.scp_connection import TimeoutError


def get_spinnaker_info(mc):
    yield "Device Type: SpiNNaker"

    yield ""

    info = mc.get_software_version(255, 255)
    yield "Software: {} v{} (Built {})".format(
        info.version_string.split("/")[0],
        ".".join(map(str, info.software_version)),
        datetime.fromtimestamp(info.build_date, tz=utc).strftime(
            '%Y-%m-%d %H:%M:%S'),
    )

    yield ""

    system_info = mc.get_system_info()
    yield "Machine dimensions: {}x{}".format(
        system_info.width, system_info.height)

    # Construct a histogram of the number of cores in the available chips
    num_chips = len(system_info)
    num_cores_hist = defaultdict(lambda: 0)
    for (x, y), chip_info in iteritems(system_info):
        num_cores_hist[chip_info.num_cores] += 1

    hist_msg = []
    for num_cores, count in sorted(iteritems(num_cores_hist), reverse=True):
        hist_msg.append("{} cores: {}".format(num_cores, count))
    yield "Working chips: {} ({})".format(num_chips, ", ".join(hist_msg))

    machine = build_machine(system_info)
    has_wrap_around_links = machine.has_wrap_around_links()
    yield "Network topology: {}".format(
        "torus" if has_wrap_around_links else "mesh"
    )

    # Links which have live cores at either end but are down
    dead_links = 0

    # Links which have a dead core at one end (and thus would be reported as
    # dead anyway)
    links_to_dead_chips = 0

    # Count dead links
    for x, y, link in system_info.dead_links():
        dx, dy = link.to_vector()
        xx, yy = x + dx, y + dy
        if has_wrap_around_links:
            xx %= system_info.width
            yy %= system_info.height
        if (x, y) in system_info and (xx, yy) in system_info:
            dead_links += 1
        else:
            links_to_dead_chips += 1

    yield "Dead links: {} (+ {} to dead/missing cores)".format(
        dead_links, links_to_dead_chips)

    yield ""

    # Report running applications. Builds a histogram {app_name: {state:
    # count}}
    yield "Application states:"
    app_states = defaultdict(lambda: defaultdict(lambda: 0))
    for (x, y), chip_info in iteritems(system_info):
        for p in range(chip_info.num_cores):
            status = mc.get_processor_status(x=x, y=y, p=p)
            app_states[status.app_name][status.cpu_state] += 1
    for app_name, states in sorted(iteritems(app_states),
                                   key=(lambda s: sum(itervalues(s[1])))):
        state_counts = []
        for state, count in sorted(iteritems(states), key=(lambda s: -s[1])):
            state_counts.append("{} {}".format(count, state.name))
        yield "    {}: {}".format(
            app_name, ", ".join(state_counts))


def get_bmp_info(bc):
    yield "Device Type: BMP"

    yield ""

    info = bc.get_software_version()
    yield "Software: {} v{} (Built {})".format(
        info.version_string.split("/")[0],
        ".".join(map(str, info.version)),
        datetime.fromtimestamp(info.build_date, tz=utc).strftime(
            '%Y-%m-%d %H:%M:%S'),
    )
    yield "Code block in use: {}".format(info.code_block)
    yield "Board ID (slot number): {}".format(info.board_id)

    yield ""

    adc = bc.read_adc(info.board_id)
    yield "1.2 V supply: {:.2f} V, {:.2f} V, {:.2f} V".format(
        adc.voltage_1_2a, adc.voltage_1_2b, adc.voltage_1_2c)
    yield "1.8 V supply: {:.2f} V".format(adc.voltage_1_8)
    yield "3.3 V supply: {:.2f} V".format(adc.voltage_3_3)
    yield "Input supply: {:.2f} V".format(adc.voltage_supply)

    yield ""

    yield "Temperature top: {:.1f} *C".format(adc.temp_top)
    yield "Temperature bottom: {:.1f} *C".format(adc.temp_btm)
    if adc.temp_ext_0 is not None:
        yield "Temperature external 0: {:.1f} *C".format(adc.temp_ext_0)
    if adc.temp_ext_1 is not None:
        yield "Temperature external 1: {:.1f} *C".format(adc.temp_ext_1)
    if adc.fan_0 is not None:
        yield "Fan 0 speed: {} RPM".format(adc.fan_0)
    if adc.fan_1 is not None:
        yield "Fan 1 speed: {} RPM".format(adc.fan_1)


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Print a summary of basic SpiNNaker machine "
                    "and BMP information")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(rig.__version__))

    parser.add_argument("hostname", type=str,
                        help="hostname or IP of SpiNNaker system or BMP")

    args = parser.parse_args(args)

    # Determine what type of machine this is and print information accordingly
    try:
        mc = MachineController(args.hostname)
        info = mc.get_software_version(255, 255)
        if "SpiNNaker" in info.version_string:
            for line in get_spinnaker_info(mc):
                print(line)
        elif "BMP" in info.version_string:
            bc = BMPController(args.hostname)
            for line in get_bmp_info(bc):
                print(line)
        else:
            sys.stderr.write("{}: error: unknown architecture '{}'\n".format(
                parser.prog, info.version_string))
            return 2
    except TimeoutError:
        sys.stderr.write("{}: error: command timed out\n".format(
            parser.prog))
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
