"""A minimal command-line utility for listening for unbooted machines.

Installed as "rig-discover" by setuptools.
"""

import sys
import argparse

import rig

from rig.machine_control.unbooted_ping import listen


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Listen for unbooted SpiNNaker boards.")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(rig.__version__))

    parser.add_argument("--timeout", "-t", type=float, default=6.0,
                        help="Time to wait before giving up.")

    args = parser.parse_args(args)

    ip_address = listen(timeout=args.timeout)

    if ip_address is not None:
        print(ip_address)
        return 0
    else:
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
