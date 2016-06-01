.. _tutorial-03:

03: Reading and Writing SDRAM - Improved
========================================

We're now going to re-write the host-program from our previous example program,
which used SpiNNaker to add two numbers together. In particular, some
higher-level facilities of the
:py:class:`~rig.machine_control.MachineController` will be used to make the
host application simpler and more robust. The SpiNNaker application kernel,
however, will remain unchanged.

The source files used in this tutorial can be downloaded below:

* Host program
    * :download:`adder_improved.py`
* SpiNNaker kernel (unchanged from :ref:`part 02 <tutorial-02>`)
    * :download:`adder.c`
    * :download:`Makefile`

Reliably stopping applications
------------------------------

Now that we're starting to allocate machine resources and write more complex
programs it is important to be sure that the ``stop`` signal is sent to the
machine at the end of our host application's execution. Rather than inserting a
call to :py:meth:`~rig.machine_control.MachineController.send_signal` into
every exit code path, Rig provides the
:py:meth:`~rig.machine_control.MachineController.application` context manager
which automatically sends a stop signal when the block ends::

    with mc.application():
        # ...Application code...

When execution leaves an
:py:meth:`~rig.machine_control.MachineController.application` block, whether by
reaching the end of the block, returning early from the function which contains
it or encountering an exception, the ``stop`` signal is sent automatically.

In our new host program, we surround our application logic with an
:py:meth:`~rig.machine_control.MachineController.application` block. The
:py:meth:`~rig.machine_control.MachineController.boot` command is purposely
placed outside the block since if the boot process fails, it is neither
necessary nor possible to send a ``stop`` signal.

File-like memory access
-----------------------

When working with SDRAM it can be easy to accidentally access memory outside
the range of an allocated buffer. To provide safer and more convenient access
to SDRAM the
:py:meth:`~rig.machine_control.MachineController.sdram_alloc_as_filelike`
method produces a file-like
:py:class:`~rig.machine_control.machine_controller.MemoryIO` object for the
allocated memory. This object can be used just like a conventional file, for
example using :py:meth:`~rig.machine_control.machine_controller.MemoryIO.read`,
:py:meth:`~rig.machine_control.machine_controller.MemoryIO.write` and
:py:meth:`~rig.machine_control.machine_controller.MemoryIO.seek` methods. All
writes and reads to the file are automatically constrained to the allocated
block of SDRAM preventing accidental corruption of memory. Additionally, users
of an allocated block of memory need not know anything about the chip or address of the
memory and may even be oblivious to the fact that they're using anything
other than a normal file. This can simplify application code by avoiding the
need to pass around additional information.

We replace the previous calls to 
:py:meth:`~rig.machine_control.MachineController.sdram_alloc`,
:py:meth:`~rig.machine_control.MachineController.write` and
:py:meth:`~rig.machine_control.MachineController.read` with:

.. literalinclude:: adder_improved.py
    :language: python
    :lines: 23,29,38

Just like files, reads and writes occur immediately after the data the previous read
and write encountered.
:py:meth:`~rig.machine_control.machine_controller.MemoryIO.seek` must be used
move the 'read head' to other locations in memory. Note that in this case since
the result value is written immediately after the two input values we do not
need to seek before reading.

In the next part of the tutorial we'll use what we've learnt to take our first
steps towards building a real application: a digital circuit simulator. Onward
to :ref:`part 04 <tutorial-04>`!
