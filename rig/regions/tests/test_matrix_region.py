import mock
import numpy as np
import pytest
import tempfile

from ..region import PrependNumAtoms
from ..matrix_region import (MatrixRegion, PrependNumColumns, PrependNumRows,
                             NpIntFormatter, RowSlicedMatrixRegion,
                             ColumnSlicedMatrixRegion)


class TestUnpartitionedMatrixRegion(object):
    @pytest.mark.parametrize("matrix, shape", [
        (np.zeros(shape=(3, 4)), (4, 3)),  # Shape mismatch
        (None, None),  # Neither matrix nor shape
    ])
    def test_init_mismatch_shape(self, matrix, shape):
        """Check that a ValueError is raised if the matrix and shape don't
        match or no matrix or shape are provided."""
        with pytest.raises(ValueError):
            MatrixRegion(matrix, shape)

    def test_too_many_dimensions(self):
        with pytest.raises(ValueError):
            MatrixRegion(np.zeros(shape=(1, 2, 3)))

    @pytest.mark.parametrize("matrix, shape, formatter, prepends, size", [
        (np.zeros(shape=(3, 4)), None, NpIntFormatter(4, np.uint32),
         list(), 3*4*4),
        (np.zeros(shape=(3)), None, NpIntFormatter(4, np.uint32),
         list(), 3*4),
        (np.zeros(shape=(3, 4)), None, NpIntFormatter(2, np.uint16),
         list(), 3*4*2),
        (None, (5, 2), NpIntFormatter(1, np.uint8), list(), 5*2*1),
        (None, (5,), NpIntFormatter(1, np.uint8), list(), 5*1),
        (None, (5, 2), NpIntFormatter(1, np.uint8),
         [PrependNumColumns(1)], 5*2*1 + 1),
    ])
    def test_sizeof(self, matrix, shape, formatter, prepends, size):
        # Create the matrix region, then assert the size is correct.
        mr = MatrixRegion(matrix=matrix, shape=shape, prepends=prepends,
                          formatter=formatter)
        assert mr.sizeof(slice(0, 0)) == size

    @pytest.mark.parametrize("matrix, shape, prepends, empty", [
        (np.zeros(shape=(3, 1)), None, list(), False),
        (None, (3, 2), [1], False),
        (None, (3, 2), [], True),
    ])
    def test_empty(self, matrix, shape, prepends, empty):
        """Test whether the `empty` flag is set correctly."""
        mr = MatrixRegion(matrix, shape, prepends)
        assert mr.empty is empty

    def test_locks_matrix(self):
        """Check that the data stored in the region is copied and not editable.
        """
        # Create the data and the matrix region
        data = np.zeros((2, 3))
        mr = MatrixRegion(data)

        # Assert that writing to data doesn't modify the region data
        data[0][1] = 2.
        assert not np.all(data == np.zeros((2, 3)))
        assert np.all(mr.matrix == np.zeros((2, 3)))

        # Assert the region data can't be written to directly
        with pytest.raises(ValueError):
            mr.matrix[0][0] = 3.
        assert mr.matrix.flags.writeable is False

    @pytest.mark.parametrize("matrix, vertex_slice", [
        (np.ones(shape=(3, 4), dtype=np.uint32), slice(0, 1)),
        (np.zeros(shape=(2, 5), dtype=np.uint32), slice(1, 4)),
    ])
    def test_write_subregion_to_file_no_prepends(self, matrix, vertex_slice):
        # Create a temporary file to write to
        f = tempfile.TemporaryFile()

        # Create the region and write out
        mr = MatrixRegion(matrix)
        mr.write_subregion_to_file(vertex_slice, f)

        # Read in the file, check that the matrices match
        f.seek(0)
        recovered = np.fromstring(
            f.read(), dtype=matrix.dtype).reshape(matrix.shape)
        assert np.all(recovered == matrix)

    @pytest.mark.parametrize("matrix, prepends, vertex_slice, prepend_data", [
        (np.ones(shape=(3, 4), dtype=np.uint32),
         [PrependNumAtoms(4)], slice(0, 1), b'\x01\x00\x00\x00'),
        (np.zeros(shape=(2, 5), dtype=np.uint32),
         [PrependNumColumns(1), PrependNumRows(1)], slice(1, 4),
         b'\x05\x02'),
    ])
    def test_write_subregion_to_file(self, matrix, prepends, vertex_slice,
                                     prepend_data):
        # Create a temporary file to write to
        f = tempfile.TemporaryFile()

        # Create a formatter
        formatter = mock.Mock(spec=NpIntFormatter)
        formatter.side_effect = NpIntFormatter(4, np.uint32)

        # Create the region and write out
        mr = MatrixRegion(matrix, prepends=prepends, formatter=formatter)
        mr.write_subregion_to_file(vertex_slice, f, subvertex_index=1)

        # Assert that the formatter was called with the data and the kwargs
        formatter.assert_called_once_with(mr.matrix, subvertex_index=1)

        # Read in the file, check that the matrices match
        f.seek(0)
        assert f.read(len(prepend_data)) == prepend_data
        recovered = np.fromstring(
            f.read(), dtype=matrix.dtype).reshape(matrix.shape)
        assert np.all(recovered == matrix)


class TestRowSlicedMatrixRegion(object):
    """Test for matrix regions which are sliced by row."""

    @pytest.mark.parametrize("matrix,shape,formatter,prepends,slice,size", [
        (np.zeros(shape=(3, 4)),
         None,
         NpIntFormatter(4, np.uint32),
         list(),
         slice(0, 1),
         1*4*4),
        (np.zeros(shape=(3, 4)),
         None,
         NpIntFormatter(4, np.uint32),
         list(),
         slice(0, 2),
         2*4*4),
        (np.zeros(shape=(3, 4)),
         None,
         NpIntFormatter(2, np.uint16),
         list(),
         slice(0, 3),
         3*4*2),
        (np.zeros(shape=(3, 1)),
         None,
         NpIntFormatter(2, np.uint16),
         list(),
         slice(0, 3),
         3*1*2),
        (np.zeros(shape=(5, 1)),
         None,
         NpIntFormatter(2, np.uint16),
         [PrependNumAtoms(4)],
         slice(2, 4),
         2*1*2 + 4),
    ])
    def test_sizeof(self, matrix, shape, formatter, prepends, slice, size):
        # Create the matrix region, then assert the size is correct.
        mr = RowSlicedMatrixRegion(
            matrix=matrix, shape=shape, prepends=prepends, formatter=formatter)
        assert mr.sizeof(slice) == size

    def test_write_subregion_to_file(self):
        """Test writing a subregion to file."""
        # Create some data which should be distinctive
        data = np.array([[1., 2., 3., 4.]]*2).T

        # Create a matrix region with prepends
        pps = [PrependNumAtoms(1), PrependNumRows(1), PrependNumColumns(1)]
        mr = RowSlicedMatrixRegion(data, prepends=pps)

        # Create temporary file to write to
        f = tempfile.TemporaryFile()

        # Write out a subregion
        mr.write_subregion_to_file(slice(0, 3), f)

        # Check that the first 3 bytes are correct
        f.seek(0)
        assert f.read(3) == b'\x03\x03\x02'

        # Check that the data is correct
        d2 = np.fromstring(f.read(), dtype=np.uint32).reshape((3, 2))
        assert np.all(d2 == data[0:3])


class TestColumnSlicedMatrixRegion(object):
    def test_write_subregion_to_file(self):
        """Test writing a subregion to file."""
        # Create some data which should be distinctive
        data = np.array([[1., 2., 3., 4.]]*2)

        # Create a matrix region with prepends
        pps = [PrependNumAtoms(1), PrependNumRows(1), PrependNumColumns(1)]
        mr = ColumnSlicedMatrixRegion(data, prepends=pps)

        # Create temporary file to write to
        f = tempfile.TemporaryFile()

        # Write out a subregion
        mr.write_subregion_to_file(slice(2, 3), f)

        # Check that the first 3 bytes are correct
        f.seek(0)
        assert f.read(3) == b'\x01\x02\x01'

        # Check that the data is correct
        d2 = np.fromstring(f.read(), dtype=np.uint32).reshape((2, 1))
        assert np.all(d2 == data.T[2:3].T)
