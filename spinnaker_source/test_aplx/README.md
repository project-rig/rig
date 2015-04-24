Rig Test Application
====================

The Rig test application is a simple program which when executed will write to
memory to indicate the progress of the application.

Writes will be made to the word at `sv->sdram_base + p*4` where `p` is the
virtual CPU number the application is running on.

The initial written value will be `(x << 24) | (y << 16) | p`.

Making the test APLX
--------------------

This should be unnecessary unless you change the source.  With the
[spinnaker_tools](https://github.com/SpiNNakerManchester/spinnaker_tools) set
up and initialised simply run:

    make

**If you change the source code please ensure that you also commit an update to
the binary to allow testing by those who do not or cannot compile the binary.**
