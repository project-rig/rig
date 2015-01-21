import functools
import numpy as np
from .region import Region, PrependedValue


class NpIntFormatter(object):
    def __init__(self, bytes_per_element, dtype):
        self.bytes_per_element = bytes_per_element
        self.dtype = dtype

    def __call__(self, matrix, **kwargs):
        return matrix.astype(dtype=self.dtype)


class MatrixRegion(Region):
    """A region of memory which represents data from a matrix.

    Notes
    -----
    """
    partition_index = None

    def __init__(self, matrix=None, shape=None, prepends=list(),
                 formatter=NpIntFormatter(4, np.uint32)):
        """Create a new region to represent a matrix data structure in memory.

        Parameters
        ----------
        matrix : :py:class:`numpy.ndarray` or None
            A matrix that will be stored in memory, or nothing to indicate that
            the data will be filled on SpiNNaker.  The matrix will be copied
            and made read-only, so provide the matrix as it is ready to go into
            memory.
        shape : tuple or None
            A tuple representing the shape of the matrix that will be stored in
            memory, or None if the matrix has already been specified.
        prepends : list of :py:class:`RegionPrepend`
            Values which will be prepended to the matrix when it is written out
            into memory.
        formatter : callable
            A formatter which will be applied to the Numpy matrix before
            writing the value out.
        """
        # Initialise the region which is empty if there is no matrix and no
        # prepends.
        super(MatrixRegion, self).__init__(
            empty=matrix is None and len(prepends) == 0,
            prepends=prepends
        )

        # Check that either a matrix or a shape are provided, otherwise raise a
        # ValueError.
        if matrix is None and shape is None:
            raise ValueError("Either a matrix or shape must be provided.")

        # Get the size of the matrix
        if shape is None:
            shape = matrix.shape

        if matrix is not None and matrix.shape != shape:
                raise ValueError("Matrix and shape do not match.")

        if len(shape) < 2:
            shape += (1, )
        elif len(shape) > 2:
            raise ValueError("Matrix may be at most 2-D")

        self.shape = shape

        # Copy and store the matrix data
        if matrix is not None:
            self.matrix = np.copy(matrix)
            self.matrix.flags.writeable = False

        # Store the formatter
        self.formatter = formatter

    def sizeof(self, vertex_slice):
        """Get the size of a slice of this region in bytes.

        See :py:method:`Region.sizeof`
        """
        # Get the size of the prepends
        pp_size = super(MatrixRegion, self).sizeof(vertex_slice)
        return (pp_size + self.size_from_shape(vertex_slice) *
                self.formatter.bytes_per_element)

    def size_from_shape(self, vertex_slice):
        """Get the size from the shape of the matrix in number of elements.

        Parameters
        ----------
        vertex_slice : :py:func:`slice`
            The slice of atoms that will be represented by the region.
        """
        # If the shape is n-D then multiply the length of the axes together,
        # accounting for the clipping of the partitioned axis.
        return functools.reduce(
            lambda x, y: x*y,
            [s if i != self.partition_index else
             (min(s, vertex_slice.stop) - max(0, vertex_slice.start)) for
             i, s in enumerate(self.shape)])

    def write_subregion_to_file(self, vertex_slice, fp, **formatter_args):
        """Write the data contained in a portion of this region out to file.
        """
        # Write out any prepends
        super(MatrixRegion, self).write_subregion_to_file(vertex_slice, fp,
                                                          **formatter_args)

        # Partition and format the data
        assert self.partition_index in [None, 0, 1]
        if self.partition_index == 0:
            data = self.matrix[vertex_slice]
        elif self.partition_index == 1:
            data = self.matrix.T[vertex_slice].T
        elif self.partition_index is None:
            data = self.matrix

        # Format the data and then write to file
        formatted = self.formatter(data, **formatter_args)
        fp.write(formatted.reshape((formatted.size, 1)).data)


class RowSlicedMatrixRegion(MatrixRegion):
    partition_index = 0


class ColumnSlicedMatrixRegion(MatrixRegion):
    partition_index = 1


class PrependNumRows(PrependedValue):
    """Prepend the number of rows in a :py:class:`MatrixRegion` to the start of
    the data in the matrix region.
    """
    def _get_prepended_value(self, vertex_slice, region):
        # If partitioning by row then return the number of atoms
        if region.partition_index == 0:
            return vertex_slice.stop - vertex_slice.start
        return region.matrix.shape[0]


class PrependNumColumns(PrependedValue):
    """Prepend the number of columns in a :py:class:`MatrixRegion` to the start
    of the data in the matrix region.
    """
    def _get_prepended_value(self, vertex_slice, region):
        # If partitioning by column then return the number of atoms
        if region.partition_index == 1:
            return vertex_slice.stop - vertex_slice.start
        return region.matrix.shape[1]
