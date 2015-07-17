"""A minimal command-line utility which lists the applications running on every
core in a SpiNNaker machine.

Installed as "rig-ps" by setuptools.
"""

import sys
import argparse

import rig

import re

from rig.machine_control import MachineController

from rig.machine_control.scp_connection import SCPError, TimeoutError

from rig.machine import Cores


def match(string, patterns):
    """Given a string return true if it matches the supplied list of
    patterns.

    Parameters
    ----------
    string : str
        The string to be matched.
    patterns : None or [pattern, ...]
        The series of regular expressions to attempt to match.
    """
    if patterns is None:
        return True
    else:
        return any(re.match(pattern, string)
                   for pattern in patterns)


def get_process_list(mc, x_=None, y_=None, p_=None,
                     app_ids=None, applications=None, states=None):
    """Scan a SpiNNaker system's cores filtering by the specified features.

    Generates
    -------
    (x, y, core, state, runtime_exception, application, app_id)
    """

    machine = mc.get_machine()
    for x, y in machine:
        if x_ is not None and x_ != x:
            continue
        if y_ is not None and y_ != y:
            continue

        for p in range(machine[(x, y)][Cores]):
            if p_ is not None and p_ != p:
                continue

            try:
                status = mc.get_processor_status(x=x, y=y, p=p)
                keep = (match(str(status.app_id), app_ids) and
                        match(status.app_name, applications) and
                        match(status.cpu_state.name, states))

                if keep:
                    yield (x, y, p,
                           status.cpu_state,
                           status.rt_code,
                           status.app_name,
                           status.app_id)
            except SCPError as e:
                # If an error occurs while communicating with a chip, we bodge
                # it into the "cpu_status" field and continue (note that it
                # will never get filtered out).
                class DeadStatus(object):
                    name = "{}: {}".format(e.__class__.__name__, str(e))
                yield (x, y, p, DeadStatus(), None, "", -1)


def main(args=None):
    parser = argparse.ArgumentParser(
        description="List all applications running on a SpiNNaker machine")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(rig.__version__))

    parser.add_argument("hostname", type=str,
                        help="hostname or IP of SpiNNaker system")

    parser.add_argument("x", type=int, nargs="?",
                        help="the X coordinate of the chip to list")
    parser.add_argument("y", type=int, nargs="?",
                        help="the Y coordinate of the chip to list")
    parser.add_argument("p", type=int, nargs="?",
                        help="the core number to list")

    parser.add_argument("--app-id", "-a", type=str, action="append",
                        help="show only applications with an application "
                             "ID matching the supplied regex")
    parser.add_argument("--name", "-n",
                        type=str, action="append",
                        help="list only cores running the application "
                             "whose name matches the supplied regex")
    parser.add_argument("--state", "-s",
                        type=str, action="append",
                        help="list only cores in states matching the "
                             "supplied regex")

    args = parser.parse_args(args)

    if args.x is not None and args.y is None:
        parser.error("both or neither of 'x' and 'y' must be specified")

    try:
        mc = MachineController(args.hostname)
        info = mc.get_software_version(0, 0)
        if "SpiNNaker" in info.version_string:
            print("X   Y   P   State             Application      App ID")
            print("--- --- --- ----------------- ---------------- ------")
            for (x, y, core, state, runtime_exception, application, app_id) \
                    in get_process_list(mc,
                                        args.x, args.y, args.p,
                                        args.app_id, args.name, args.state):
                print("{:3d} {:3d} {:3d} "
                      "{:17s} "
                      "{:16s} "
                      "{:6d} "
                      "{:s}".format(x, y, core,
                                    state.name,
                                    application,
                                    app_id,
                                    runtime_exception.name
                                    if runtime_exception else ""))
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
