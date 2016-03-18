"""A minimal command-line utility for booting SpiNNaker machines.

Installed as "rig-boot" by setuptools.
"""

import sys
import argparse

import rig

from rig.machine_control import boot, MachineController

from rig.machine_control.machine_controller import SpiNNakerBootError

BOOT_OPTION_POSTFIX = "_boot_options"
"""Postfix for boot option dicts in boot."""


def main(args=None):
    parser = argparse.ArgumentParser(description="Boot a SpiNNaker board")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(rig.__version__))

    parser.add_argument("hostname", type=str,
                        help="hostname or IP of SpiNNaker system")

    # Automatically build a list of available machine parameters by inspecting
    # boot module.
    type_group = parser.add_mutually_exclusive_group()
    for dict_name in dir(boot):
        if dict_name.endswith(BOOT_OPTION_POSTFIX):
            type_name = dict_name[:-len(BOOT_OPTION_POSTFIX)]
            option_name = "--{}".format(type_name)
            option_dict = getattr(boot, dict_name)
            option_help = "use predefined boot options for a {} board".format(
                type_name)
            type_group.add_argument(option_name, action="store_const",
                                    const=option_dict, default={},
                                    dest="board_options",
                                    help=option_help)

    args = parser.parse_args(args)

    # Attempt to boot the machine
    mc = MachineController(args.hostname)
    try:
        if mc.boot(**args.board_options):
            return 0
        else:
            # The machine was already booted.
            sys.stderr.write(
                "{}: error: machine already booted.\n".format(parser.prog))
            return 1
    except SpiNNakerBootError as e:
        # The machine could not be booted for some reason; show an appropriate
        # message
        sys.stderr.write("{}: error: {}\n".format(parser.prog, str(e)))
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
