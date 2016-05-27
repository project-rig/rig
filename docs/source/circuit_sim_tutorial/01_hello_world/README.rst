.. _tutorial-01:

01: Hello World
===============

In this classic example we make a SpiNNaker application which simply prints
"Hello, world!" on one core and then exits.

The source files used in this tutorial can be downloaded below:

* Host program
    * :download:`hello.py`
* SpiNNaker kernel
    * :download:`hello.c`
    * :download:`Makefile`

As is tradition our first application will simply print 'Hello, world!' and
exit. In this application our SpiNNaker application kernel will simply write
its greeting into memory on a SpiNNaker chip and then terminate. Our host
program will:

* Load the application kernel
* Instruct SpiNNaker to run it
* Wait for the kernel to terminate
* Retrieve and print the message from SpiNNaker's memory
* Clean up and quit

SpiNNaker Application Kernel
----------------------------

We start by writing the SpiNNaker application kernel itself which consists of a
single call to ``io_printf`` in ``hello.c``.

.. literalinclude:: hello.c
    :language: c
    :lines: 5,7-10

This call writes our famous message to the "IO buffer", an area of system
memory in each SpiNNaker chip which we can later read back from the host.

To compile our application we can use the standard two-line makefile:

.. literalinclude:: Makefile
    :language: Makefile

To produce a compiled ``hello.aplx`` file ready for loading onto SpiNNaker,
simply type::

    $ make

.. note::
    
    This makefile presumes your shell environment is set up correctly to use
    the 'spinnaker_tools'. This can be done by running::
    
        $ source /path/to/spinnaker_tools/setup


Host-side application
---------------------

Now that we have our compiled binary we must boot our SpiNNaker machine, load
our application onto a core and then read back the IO buffer. We *could* do
this using the `ybug` command included with 'spinnaker_tools' but since we're
building up towards a real application we'll write a Python program which will
automate all these steps.

.. note::

    Even though we'll be writing our host programs in Python without using
    'ybug', the 'ybug' tool remains a very useful debugging aid during
    development can can be safely used alongside your host application.

In our host program we'll use a part of the 'Rig' library called
:py:class:`~rig.machine_control.MachineController` which provides a high-level
interface for communicating with and controlling SpiNNaker machines. The first
step in our program is to create an instance of the
:py:class:`~rig.machine_control.MachineController` class to communicate with
our SpiNNaker board:

.. literalinclude:: hello.py
    :language: python
    :lines: 6,8,11

Note that we take the hostname/IP of the board as a command-line argument to
avoid hard-coding it into our script.

Next to boot the machine we use the
:py:meth:`~rig.machine_control.MachineController.boot` method. If the machine
is already booted, this command does nothing.

.. literalinclude:: hello.py
    :language: python
    :lines: 14

Next we'll load our application using the
:py:meth:`~rig.machine_control.MachineController.load_application` method.
This method loads our application onto core 1 of chip (0, 0), checks it was
loaded successfully and then starts the program executing.

.. literalinclude:: hello.py
    :language: python
    :lines: 17

.. note::

    :py:meth:`~rig.machine_control.MachineController.load_application` can load
    an application onto many cores on many chips at once, hence the slightly
    unusual syntax.

When a SpiNNaker application kernel's ``c_main`` function returns, the
application goes into the ``exit`` state. By using
:py:meth:`~rig.machine_control.MachineController.wait_for_cores_to_reach_state`
we can wait for our hello world application to finish executing.

.. literalinclude:: hello.py
    :language: python
    :lines: 20

After our application has exited we can fetch and print out the contents of the
IO buffer to retrieve the message printed by the application kernel using
:py:meth:`~rig.machine_control.MachineController.get_iobuf`. By convention Rig
uses the name ``p`` -- for processor -- when identifying cores.

.. literalinclude:: hello.py
    :language: python
    :lines: 23

As a final step we must send the "stop" signal to SpiNNaker using
:py:meth:`~rig.machine_control.MachineController.send_signal`. This frees up
any resources allocated during the running of our application.

.. literalinclude:: hello.py
    :language: python
    :lines: 26


Running our application
-----------------------

Our script is now finished and can then be executed like so::

    $ python hello.py BOARD_IP_HERE
    Hello, world!

.. note::

    The :py:meth:`~rig.machine_control.MachineController.boot` command can take
    a few seconds to complete if the machine is not already booted. If the
    machine is already booted, the script should run almost instantaneously.

Once the excitement of being greeted by a super computer has worn off, its time
to set SpiNNaker to work on some 'real' computation. Lets head onward to
:ref:`part 02 <tutorial-02>`.
