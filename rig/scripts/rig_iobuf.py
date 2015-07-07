"""A minimal command-line utility which prints the IOBUF data for a specified
core.

Installed as "rig-iobuf" by setuptools.
"""

import sys
import argparse

import rig

from rig.machine_control import MachineController

from rig.machine_control.scp_connection import TimeoutError


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Print the contents of IOBUF for a specified core")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(rig.__version__))

    parser.add_argument("hostname", type=str,
                        help="hostname or IP of SpiNNaker system")

    parser.add_argument("x", type=int,
                        help="the X coordinate of the chip")
    parser.add_argument("y", type=int,
                        help="the Y coordinate of the chip")
    parser.add_argument("p", type=int,
                        help="the processor number")

    args = parser.parse_args(args)

    try:
        mc = MachineController(args.hostname)
        info = mc.get_software_version(0, 0)
        if "SpiNNaker" in info.version_string:
            sys.stdout.write(mc.get_iobuf(args.p, args.x, args.y))
        else:
            sys.stderr.write("{}: error: unknown architecture '{}'\n".format(
                parser.prog, info.version_string.strip("\x00")))
            return 2
    except TimeoutError:
        sys.stderr.write("{}: error: command timed out\n".format(
            parser.prog))
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
