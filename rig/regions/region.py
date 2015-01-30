import struct


class Region(object):
    """Represents a region of data in the memory of a SpiNNaker core (SDRAM or
    DTCM).

    Attributes
    ----------
    empty : bool
        Indicates that this region doesn't contain any data but is a
        placeholder for data that will be written by the SpiNNaker machine.
    prepends : list of :py:class:`PrependedValue` objects
        Values that should be prepended to region data when it is written out.
    """
    def __init__(self, empty=False, prepends=list()):
        """Create a new region, marking it as empty or filled.

        Attributes
        ----------
        empty : bool
            Indicates that this region doesn't contain any data but is a
            placeholder for data that will be written by the SpiNNaker machine.
        prepends : list of :py:class:`PrependedValue` objects
            Values that should be prepended to region data when it is written
            out.
        """
        self.empty = empty
        self.prepends = prepends[:]

    def sizeof(self, vertex_slice):
        """Get the size requirements of the region in bytes.

        Parameters
        ----------
        vertex_slice : :py:func:`slice`
            A slice object which indicates which rows, columns or other
            elements of the region should be included.

        Returns
        -------
        int
            The number of bytes required to store the data in the given slice
            of the region.

        Note
        ----
        In :py:class:`Region` this method returns the size of the prepends,
        through judicious use of :py:func:`super` one can get this
        functionality for free.
        """
        return sum(p.n_bytes for p in self.prepends)

    def write_subregion_to_file(self, vertex_slice, fp, **formatter_args):
        """Write a portion of the region to a file applying the formatter.

        Parameters
        ----------
        vertex_slice : :py:func:`slice`
            A slice object which indicates which rows, columns or other
            elements of the region should be included.
        fp : file-like object
            The file-like object to which data from the region will be written.
            This must support a `write` method.
        formatter_args : optional
            Arguments which will be passed to the (optional) formatter along
            with each value that is being written.

        Notes
        -----
        Data which falls within the slice will be written to the file after
        being formatted by any appropriate formatter.

        :py:class:`Region` implements this function to write the prepended
        values to the file.  Use of :py:func:`super` should allow reuse of this
        functionality.
        """
        # Write out the prepend values
        for p in self.prepends:
            fp.write(p(vertex_slice, self))


class PrependedValue(object):
    """Represents a value that should be prepended to the data contained within
    a region.

    Attributes
    ----------
    n_bytes : int
        The number of bytes that should be used to represent the value.
    """

    def __init__(self, n_bytes, signed=False):
        """Create a new prepended value.

        Parameters
        ----------
        n_bytes : int
            The number of bytes that should be used to represent the value that
            will be prepended to the region's data.
        signed : bool
            Whether the value that is to be prepended should be signed or
            unsigned.
        """
        # Check that the number of bytes is sane
        if n_bytes not in [1, 2, 4]:
            raise ValueError("n_bytes: {}: A prepended value can only be "
                             "1, 2 or 4 bytes long.".format(n_bytes))

        self.n_bytes = n_bytes
        self.signed = signed

    def __call__(self, vertex_slice, region):
        """Return a bytestring containing the value that is to be prepended.

        Parameters
        ----------
        vertex_slice : :py:func:`slice`
            A slice object indicating which atoms from the region should be
            included.
        region : :py:class:`Region`
            The region that this value will be prepended to, used to compute
            the value.

        Returns
        -------
        bytestring
            A bytestring of `n_bytes` containing a value to be prepended to a
            region's data.
        """
        if (vertex_slice.start is None or vertex_slice.stop is None or
                vertex_slice.start > vertex_slice.stop):
            raise ValueError(vertex_slice)

        return self._format_value(
            self._get_prepended_value(vertex_slice, region)
        )

    def _format_value(self, value):
        """Get the bytestring representation of a value."""
        # Get the correct character to pack with
        c = {1: 'b', 2: 'h', 4: 'i'}[self.n_bytes]

        # Pack and return
        return bytes(struct.pack('<{}'.format(c if self.signed else c.upper()),
                                 value))

    def _get_prepended_value(self, vertex_slice, region):
        """Get the value to prepend to the region data.

        This method is called by :py:func:`__call__`. Override this method to
        provide the value to prepend.
        """
        raise NotImplementedError


class PrependNumAtoms(PrependedValue):
    """Prepend the number of atoms in the vertex to the data in a region."""
    def __init__(self, n_bytes):
        super(PrependNumAtoms, self).__init__(n_bytes, signed=False)

    def _get_prepended_value(self, vertex_slice, region):
        return vertex_slice.stop - vertex_slice.start
