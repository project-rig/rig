.. _tutorial-02:

02: Reading and Writing SDRAM
=============================

Most interesting SpiNNaker application kernels require some sort of
configuration data and produce result data which must be loaded and read back
from the machine before and after executing respectively. As a result, a
typical host program will:

* Allocate some memory on any SpiNNaker chips where an application kernel is to
  be loaded
* Write configuration data into this memory
* Load and run the application kernel
* Read and process result data written to memory by the kernel

To illustrate this process we'll make a SpiNNaker application kernel which
reads pair of 32-bit integers from memory, adds them together, stores the
result back into memory and exits.

Much of the code in this example is unchanged from the previous example so we
will only discuss the changes.

The source files used in this tutorial can be downloaded below:

* Host program
    * :download:`adder.py`
* SpiNNaker kernel
    * :download:`adder.c`
    * :download:`Makefile`


Allocating SDRAM from the host
------------------------------

In our application, as in most real world applications, we'll use the on-chip
SDRAM (shared between all cores on a chip) to load our two integers and store
the result. By convention, the host program is responsible for allocating space
in SDRAM.

The Rig :py:class:`~rig.machine_control.MachineController` class provides an
:py:meth:`~rig.machine_control.MachineController.sdram_alloc` method which
we'll use to allocate 12 bytes of SDRAM on a SpiNNaker chip. In this example
we'll allocate some SDRAM on chip (0, 0). The first 8 bytes will contain the
two numbers to be summed and will be written by our host program. The last four
bytes will be written by the SpiNNaker application kernel and will contain the
resulting sum.

.. literalinclude:: adder.py
    :language: python
    :lines: 20

The :py:meth:`~rig.machine_control.MachineController.sdram_alloc` method
returns the address of a block of SDRAM on chip (0, 0) which was allocated.

We also need to somehow inform the SpiNNaker application kernel of this
address. To do this we can use the 'tag' argument to identify the allocated
memory block. Later, once the application kernel has been loaded it can use
``sark_tag_ptr()`` to discover the address of tagged SDRAM blocks. In most
applications, memory used by an application running on core 1 is given tag 1,
memory for core 2 is given tag 2 and so on. Since an application kernel can
discover the core number it is running on using ``spin1_get_core_id()``, the
following line gets a pointer to the SDRAM block allocated for a particular
core's application.

.. literalinclude:: adder.c
    :language: c
    :lines: 13

.. note::
    
    Tags are assigned for a single SpiNNaker chip: tag numbers can be re-used
    on other chips.


Writing SDRAM from the host
---------------------------

After allocating our block of SDRAM we must populate it with the numbers to be
added together. In this example, we pick two random numbers and, using Python's
:py:mod:`struct` module, pack them into 8 bytes.

.. literalinclude:: adder.py
    :language: python
    :lines: 23-25

.. note::

    The '<' prefix *must* be included in the struct format string to indicate
    that the data should be arranged in the little-endian order used by
    SpiNNaker.

The :py:meth:`~rig.machine_control.MachineController.write` method of the
:py:class:`~rig.machine_control.MachineController` is then used to write this
value into the first 8 bytes of the SDRAM block we allocated.

.. literalinclude:: adder.py
    :language: python
    :lines: 26

.. warning::
    
    The :py:meth:`~rig.machine_control.MachineController.write` method will
    attempt to perform any write you specify and should be used with care to
    avoid data corruption or illigal memory accesses by accidentally writing
    too much data.

Running the application kernel
------------------------------

With the SDRAM allocated, tagged and populated with data, we can now load our
application kernel as in the previous example using
:py:meth:`~rig.machine_control.MachineController.load_application`.

The application kernel adds together the numbers at the memory address
discovered by ``sark_tag_ptr()``, writes the result into memory and exits:

.. literalinclude:: adder.c
    :language: c
    :lines: 16

.. note::

    In a SpiNNaker application kernel, though SDRAM *can* be accessed directly
    like this, 'real' application kernels often use DMA to improve performance.


Reading and writing SDRAM from the host
---------------------------------------

After waiting for the application kernel to exit, the host can read the answer
back using :py:meth:`~rig.machine_control.MachineController.read` and unpack it
using Python's :py:mod:`struct` module.

.. literalinclude:: adder.py
    :language: python
    :lines: 35-37

As before, the last step is to send a "stop" signal to SpiNNaker using
:py:meth:`~rig.machine_control.MachineController.send_signal`. This signal will
automatically free all allocated blocks of SDRAM.

In this tutorial we used some fairly low-level APIs for accessing SpiNNaker's
memory. In the next tutorial we'll use some of Rig's higher-level APIs to make
the process of accessing SpiNNaker's memory and cleaning up after an
application easier and safer. Continue to :ref:`part 03 <tutorial-03>`.
