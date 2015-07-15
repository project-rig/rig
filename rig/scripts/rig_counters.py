"""A minimal command-line utility which samples counter values around the
machine.

Installed as "rig-counters" by setuptools.
"""

import sys
import argparse
import subprocess
import time

import rig

from six import iteritems
from six.moves import input

from rig.machine_control import MachineController

from rig.machine_control.machine_controller import RouterDiagnostics

from rig.machine_control.scp_connection import TimeoutError


def sample_counters(mc, machine):
    """Sample every router counter in the machine."""
    return {
        (x, y): mc.get_router_diagnostics(x, y) for (x, y) in machine
    }


def deltas(last, now):
    """Return the change in counter values (accounting for wrap-around)."""
    return {
        xy: RouterDiagnostics(*((n - l) & 0xFFFFFFFF
                                for l, n in zip(last[xy], now[xy])))
        for xy in last
    }


def monitor_counters(mc, output, counters, detailed, f):
    """Monitor the counters on a specified machine, taking a snap-shot every
    time the generator 'f' yields."""
    # Print CSV header
    output.write("time,{}{}\n".format("x,y," if detailed else "",
                                      ",".join(counters)))

    machine = mc.get_machine()

    # Make an initial sample of the counters
    last_counter_values = sample_counters(mc, machine)

    start_time = time.time()

    for _ in f():
        # Snapshot the change in counter values
        counter_values = sample_counters(mc, machine)
        delta = deltas(last_counter_values, counter_values)
        last_counter_values = counter_values

        now = time.time() - start_time

        # Output the changes
        if detailed:
            for x, y in machine:
                output.write("{:0.1f},{},{},{}\n".format(
                    now, x, y,
                    ",".join(str(getattr(delta[(x, y)], c))
                             for c in counters)))
        else:
            totals = [0 for _ in counters]
            for xy in machine:
                for i, counter in enumerate(counters):
                    totals[i] += getattr(delta[xy], counter)
            output.write("{:0.1f},{}\n".format(
                now, ",".join(map(str, totals))))


def press_enter(multiple=False, silent=False):
    """Return a generator function which yields every time the user presses
    return."""

    def f():
        try:
            while True:
                if silent:
                    yield input()
                else:
                    sys.stderr.write("<press enter> ")
                    sys.stderr.flush()
                    yield input()
                if not multiple:
                    break
        except (EOFError, KeyboardInterrupt):
            # User Ctrl+D or Ctrl+C'd
            if not silent:
                # Prevents the user's terminal getting clobbered
                sys.stderr.write("\n")
                sys.stderr.flush()
            return

    return f


def run_command(command):
    """Return a generator function which yields once when a supplied command
    exits."""
    def f():
        try:
            subprocess.call(command)
        except KeyboardInterrupt:
            # If the user interrupts the process, just continue
            pass
        yield ""
    return f


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Report changes in router diagnostic counters in a "
                    "SpiNNaker system.")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(rig.__version__))

    parser.add_argument("hostname", type=str,
                        help="hostname or IP of SpiNNaker system")

    parser.add_argument("--detailed", "-d", action="store_true",
                        help="give counter values for each chip individually "
                             "by default, just a sum is given")
    parser.add_argument("--silent", "-s", action="store_true",
                        help="do not produce informational messages on STDOUT")
    parser.add_argument("--output", "-o", type=str, default="-",
                        metavar="FILENAME",
                        help="filename to write recorded counter values to "
                             "or - for stdout (default: %(default)s)")

    when_group = parser.add_mutually_exclusive_group()
    when_group.add_argument("--command", "-c", nargs=argparse.REMAINDER,
                            help="report the difference in counter values "
                                 "before and after executing the supplied "
                                 "command")
    when_group.add_argument("--multiple", "-m", action="store_true",
                            help="allow recording of multiple snapshots "
                                 "(default: just one snapshot)")

    counter_group = parser.add_argument_group(
        "counter selection arguments",
        description="Any subset of these counters may be selected for output. "
                    "If none are specified, only dropped multicast packets "
                    "will be reported.")
    abbreviations = {
        "local": "loc",
        "external": "ext",
        "dropped": "drop",
        "multicast": "mc",
        "nearest-neighbour": "nn",
        "fixed-route": "fr",
        "counter": "c",
    }
    for counter in RouterDiagnostics._fields:
        arg_name = "--{}".format(counter.replace("_", "-"))
        short_name = arg_name
        for full, abbrev in iteritems(abbreviations):
            short_name = short_name.replace(full, abbrev)
        counter_group.add_argument(arg_name, short_name,
                                   dest="counters",
                                   action="append_const", const=counter)

    args = parser.parse_args(args)

    try:
        mc = MachineController(args.hostname)
        info = mc.get_software_version(0, 0)
        if "SpiNNaker" in info.version_string:
            counters = args.counters or ["dropped_multicast"]
            if args.output == "-":
                output = sys.stdout
            else:
                output = open(args.output, "w")

            if args.command is None:
                f = press_enter(args.multiple, args.silent)
            else:
                f = run_command(args.command)

            try:
                monitor_counters(mc, output, counters, args.detailed, f)
            finally:
                if output is not sys.stdout:  # pragma: no branch
                    output.close()  # pragma: no branch
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
