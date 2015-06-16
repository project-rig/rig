"""
Many applications require end-users to supply the details of a SpiNNaker system
they wish to connect to. This module hopes to provide a more-friendly user
interaction than just asking for an IP address and system dimensions in the
general case.

This module contains a number of wizards which extract various pieces of
information from a user by asking simple questions. A wizard is a generator
function which generates sequences of questions to which the answers are fed
back into the generator. For command-line applications, a wrapper script
:py:func:`~rig.wizard.cli_wrapper` will do all the heavy-lifting::

    >> from rig.wizard import (
    ..     dimensions_wizard, ip_address_wizard, cat, cli_wrapper)
    >> resp = cli_wrapper(cat(dimensions_wizard(), ip_address_wizard()))
    What type of SpiNNaker system to you have?
        0: A single four-chip 'SpiNN-3' board
        1: A single forty-eight-chip 'SpiNN-5' board
        2: Multiple forty-eight-chip 'SpiNN-5' boards
        3: Other
    Select an option 0-3: 2

    How many 'SpiNN-5' boards are in the system?
    > 24

    Would you like to auto-detect the SpiNNaker system's IP address?
        0: Auto-detect
        1: Manually Enter IP address or hostname
    Select an option 0-1 (default: 0):

    Make sure the SpiNNaker system is switched on and is not booted.
    <Press enter to continue>

    Discovering attached SpiNNaker systems...

    >> resp
    {'ip_address': '192.168.240.253', 'dimensions': (48, 24)}

Third-parties whose needs are not met by the supplied CLI wizard interface are
encouraged to build their own front-ends which support the wizard protocol. The
wizard generator functions generate the following objects:

* :py:class:`~rig.wizard.MultipleChoice` This tuple includes a question to be
  presented to the user along with a list of valid options to choose from and
  a default value to select (or None if no default exists). The generator
  should be sent the index of the user's selection.
* :py:class:`~rig.wizard.Text` This tuple includes a question to be
  presented to the user.  The generator should be sent the user's free-form
  text response as a string.
* :py:class:`~rig.wizard.Prompt` This tuple indicates the user should be shown
  a message which they should read and acknowledge. No response is expected.
* :py:class:`~rig.wizard.Info` This tuple indicates the user should be shown
  a message to which no response is required.

When the information has been collected successfully,
:py:exc:`~rig.wizard.Success` is raised by the wizard with a `data` attribute
containing a dictionary with the information gathered by the wizard. If the
wizard fails, a :py:exc:`~rig.wizard.Failure` exception is thrown with a
human-readable message.
"""

from collections import namedtuple

import re

from six.moves import input

from rig.machine_control.unbooted_ping import listen

from rig.geometry import standard_system_dimensions


MultipleChoice = namedtuple("MultipleChoice", "question,options,default")
Text = namedtuple("Text", "question")
Prompt = namedtuple("Prompt", "message")
Info = namedtuple("Info", "message")


class Failure(Exception):
    """Indicates that the wizard couldn't determine the information
    requested. The message indicates the reason."""


class Success(Exception):
    """The wizard successfully gathered the information requested.

    Attributes
    ==========
    data : dict
        A dictionary containing the information requested.
    """

    def __init__(self, data):
        super(Success, self).__init__()
        self.data = data

    def __str__(self):
        return str(self.data)


def dimensions_wizard():
    """A wizard which attempts to determine the dimensions of a SpiNNaker
    system.

    Returns ``{"dimensions": (x, y)}`` via the :py:exc:`~rig.wizard.Success`
    exception.
    """
    option = yield MultipleChoice(
        "What type of SpiNNaker system to you have?",
        ["A single four-chip 'SpiNN-3' board",
         "A single forty-eight-chip 'SpiNN-5' board",
         "Multiple forty-eight-chip 'SpiNN-5' boards",
         "Other"],
        None)
    assert 0 <= option < 4

    if option == 0:
        raise Success({"dimensions": (2, 2)})
    elif option == 1:
        raise Success({"dimensions": (8, 8)})
    elif option == 2:
        # Infer the system's dimensions from the number of boards supplied
        num_boards = yield Text("How many 'SpiNN-5' boards are in the system?")
        try:
            w, h = standard_system_dimensions(int(num_boards))
        except ValueError:
            # May fail due to integer conversion or the function rejecting the
            # number of boards.
            raise Failure(
                "'{}' is not a valid number of boards.".format(num_boards))
        raise Success({"dimensions": (w, h)})
    else:
        dimensions = yield Text(
            "What are the dimensions of the network in chips (e.g. 24x12)?")
        match = re.match(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", dimensions)
        if not match:
            raise Failure("'{}' is not a valid system size.".format(
                dimensions))
        else:
            w = int(match.group(1))
            h = int(match.group(2))
            raise Success({"dimensions": (w, h)})


def ip_address_wizard():
    """A wizard which attempts to determine the IP of a SpiNNaker system.

    Returns ``{"ip_address": "..."}`` via the :py:exc:`~rig.wizard.Success`
    exception.
    """
    option = yield MultipleChoice(
        "Would you like to auto-detect the SpiNNaker system's IP address?",
        ["Auto-detect",
         "Manually Enter IP address or hostname"],
        0)
    assert 0 <= option < 2

    if option == 0:
        yield Prompt(
            "Make sure the SpiNNaker system is switched on and is not booted.")
        yield Info("Discovering attached SpiNNaker systems...")
        ip_address = listen()
        if ip_address is None:
            raise Failure(
                "Did not discover a locally connected SpiNNaker system.")
    elif option == 1:  # pragma: no branch
        ip_address = yield Text(
            "What is the IP address or hostname of the SpiNNaker system?")
        if ip_address == "":
            raise Failure("No IP address or hostname entered")

    raise Success({"ip_address": ip_address})


def cat(*wizards):
    """A higher-order wizard which is the concatenation of a number of other
    wizards.

    The resulting data is the union of all wizard outputs.
    """
    data = {}

    for wizard in wizards:
        try:
            response = None
            while True:
                response = yield wizard.send(response)
        except Success as s:
            data.update(s.data)

    raise Success(data)


def cli_wrapper(generator):
    """Given a wizard, implements an interactive command-line human-friendly
    interface for it.

    Parameters
    ----------
    generator
        A generator such as one created by calling
        :py:func:`rig.wizard.wizard_generator`.

    Returns
    -------
    dict or None
        Returns a dictionary containing the results of the wizard or None if
        the wizard failed.
    """
    first = True
    response = None
    while True:
        # Insert blank lines between prompts
        if not first:
            print()
        first = False

        try:
            message = generator.send(response)

            if isinstance(message, MultipleChoice):
                print(message.question)
                for num, choice in enumerate(message.options):
                    print("    {}: {}".format(num, choice))
                option = input("Select an option 0-{}{}: ".format(
                    len(message.options) - 1,
                    " (default: {})".format(message.default)
                    if message.default is not None else ""))

                if option == "" and message.default is not None:
                    option = message.default

                try:
                    response = int(option)
                except ValueError:
                    response = -1
                if not (0 <= response < len(message.options)):
                    print("ERROR: {} is not a valid option.".format(option))
                    return None
            elif isinstance(message, Text):
                print(message.question)
                response = input("> ")
            elif isinstance(message, Prompt):
                print(message.message)
                input("<Press enter to continue>")
                response = None
            elif isinstance(message, Info):  # pragma: no branch
                print(message.message)
                response = None

        except Failure as f:
            print("ERROR: {}".format(str(f)))
            return None
        except Success as s:
            return s.data
