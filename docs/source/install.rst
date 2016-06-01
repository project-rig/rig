.. _installation:

Installation
============

.. note::

    Since Rig is a library rather than a standalone tool, most end-users will
    find that it is automatically installed as a dependency of some other
    application which they have installed, rendering these steps unecessary.


From PyPI via ``pip`` (Recommended)
-----------------------------------

The latest stable release can be installed from the `Python Package
Index <https://pypi.python.org/pypi/rig/>`_ using::

    $ pip install rig

Note that if you do not already have Numpy installed, this will be downloaded
by the above command and may take some time to install.

From source
-----------

You can install Rig from `downloaded source code
<https://github.com/project-rig/rig>`_ using setuptools as usual::

    $ git clone https://github.com/project-rig/rig.git rig
    $ cd rig
    $ python setup.py install

If you intend to work on Rig itself, take a look at
the `DEVELOP.md <https://github.com/project-rig/rig/blob/master/DEVELOP.md>`_
file in the repository for instructions on setting up a suitable development
environment and running tests etc.

Optional Extras
---------------

The following extra packages may also be installed in addition to Rig to enable
additional functionality.

``rig_c_sa`` (for faster placement)
```````````````````````````````````

::

    $ pip install rig_c_sa

The `rig_c_sa <https://github.com/project-rig/rig_c_sa>`_ library is used by
the :py:class:`~rig.place_and_route.place.sa.c_kernel.CKernel` for the
:py:func:`simulated annealing placement algorithm
<rig.place_and_route.place.sa.place>`. This kernel, written in C, can be
50-150x faster than the
:py:class:`~rig.place_and_route.place.sa.python_kernel.PythonKernel` supplied
in the basic Rig installation.
