"""A minimal command-line utility for powering on/off SpiNNaker machines via
the BMP.

Installed as "rig-power" by setuptools.
"""

import sys
import argparse

from six import next

import rig

from rig.machine_control import BMPController

from rig.machine_control.scp_connection import TimeoutError

ON_CHOICES = "on 1".split()
OFF_CHOICES = "off 0".split()


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Control SpiNNaker board power (via a BMP)")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(rig.__version__))

    parser.add_argument("hostname", type=str,
                        help="hostname or IP of a SpiNNaker board BMP")

    parser.add_argument("state", type=str, default=ON_CHOICES[0], nargs="?",
                        choices=ON_CHOICES + OFF_CHOICES)

    parser.add_argument("-b", "--board", type=str, default="0-23",
                        help="board number (e.g. 0) "
                             "or range of boards (e.g.  1,3,4-6)")

    parser.add_argument("-d", "--power-on-delay", type=float, default=None,
                        help="specify delay (seconds) after power on "
                             "command completes")

    args = parser.parse_args(args)

    # To power on, or to power off, that is the question
    if args.state in ON_CHOICES:
        state = True
    elif args.state in OFF_CHOICES:  # pragma: no branch
        state = False

    # Check power-on-delay range
    if args.power_on_delay is not None and args.power_on_delay < 0.0:
        parser.error("power on delay must be positive")

    # Parse the board number range
    boards = set()
    range_specs = args.board.split(",")
    for range_spec in range_specs:
        left, sep, right = map(str.strip, range_spec.partition("-"))
        try:
            if sep:
                if right.startswith("-"):
                    raise ValueError()
                left = int(left)
                right = int(right)
                if left > right or left < 0 or right < 0:
                    raise ValueError()
                boards.update(range(int(left), int(right) + 1))
            else:
                boards.add(int(left))
        except ValueError:
            parser.error("'{}' is not a valid board/range".format(
                range_spec))

    bc = BMPController(args.hostname)
    try:
        # Check that the device is a actually BMP
        info = bc.get_software_version(board=next(iter(boards)))
        if "BMP" not in info.version_string:
            sys.stderr.write("{}: error: device is not a BMP\n".format(
                parser.prog))
            return 2

        # Actually send the command
        if args.power_on_delay is None:
            bc.set_power(state=state, board=boards)
        else:
            bc.set_power(state=state, board=boards,
                         post_power_on_delay=args.power_on_delay)
    except TimeoutError:
        sys.stderr.write("{}: error: bmp did not respond to command\n".format(
            parser.prog))
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
