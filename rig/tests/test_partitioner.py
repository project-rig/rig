import mock
import pytest
from .. import partitioner
from ..netlist import Net


# Create a silly constraint
class WidgetConstraint(partitioner.Constraint):
    def get_usage(self, obj, obj_slice):
        # The number of widgets is the number of atoms
        return ((obj_slice.stop - obj_slice.start)*obj.multiplier +
                obj.offset)


# And a silly object
class ObjectWithWidgets(object):
    def __init__(self, n_atoms, widget_multiplier=1., widget_offset=0):
        self.n_atoms = n_atoms
        self.multiplier = widget_multiplier
        self.offset = widget_offset


class Vertex(object):
    """Represents an object that could be the source or sink of a net."""
    pass


class TestPartition(object):
    """Test operation of the partitioner."""

    @pytest.mark.parametrize(
        "obj, constraints, n_slices",
        [(ObjectWithWidgets(10), [WidgetConstraint(5)], 2),
         (ObjectWithWidgets(11), [WidgetConstraint(5),
                                  WidgetConstraint(2)], 6),
         (ObjectWithWidgets(11), [WidgetConstraint(5),
                                  WidgetConstraint(12),
                                  WidgetConstraint(2)], 6),
         (ObjectWithWidgets(10, widget_offset=3),
          [WidgetConstraint(5)], 5),  # This requires multiple attempts
         ])
    def test_partition(self, obj, constraints, n_slices):
        # Call the partitioner and check that the number of slices returned is
        # as expected.
        assert len(partitioner.partition(obj, constraints)) == n_slices

    def test_partition_fail(self):
        """Test that we raise an error if no partitioning can be made."""
        obj = ObjectWithWidgets(10, widget_multiplier=2.)
        con = WidgetConstraint(1)

        with pytest.raises(partitioner.PartitioningFailedError):
            partitioner.partition(obj, [con])


class TestConstraint(object):
    @pytest.mark.parametrize(
        "max, target, sl, cuts",
        [(10, 1.0, slice(0, 10), 1),  # Basic check
         (11, 0.5, slice(0, 10), 2),  # Checks that the target is accounted for
         (15, 0.2, slice(0, 9), 3),  # Checks that rounding up occurs
         ])
    def test_call(self, max, target, sl, cuts):
        """Test that calling a constraint object will (1) call `get_usage` and
        (2) return the correct number of cuts.
        """
        # Create the new constraint
        c = partitioner.Constraint(max=max, target=target)

        # Create a mock get_usage so that we can assert calls were made.  The
        # usage getter will just return the number of atoms in the slice.
        c.get_usage = mock.Mock(spec_set=[])
        c.get_usage.side_effect = lambda obj, obj_slice: (obj_slice.stop -
                                                          obj_slice.start)

        # Call the constraint with the slice and get the return value
        obj = mock.Mock(spec_set=[])
        assert c(obj, sl) == cuts

        # Assert that the usage getter was called
        c.get_usage.assert_called_once_with(obj, sl)


class TestSplitSlice(object):
    @pytest.mark.parametrize(
        "sl, splits",
        [(slice(None), 1),
         (slice(0, None), 1),
         (slice(-1, 1), 1),
         (slice(4, 3), 1),
         (slice(None, 3), 1),
         (slice(0, 1, 2), 1),
         (slice(0, 1), 0.5),
         (slice(0, 1), 0),
         (slice(0, 1), -1),
         ])
    def test_invalid_params(self, sl, splits):
        with pytest.raises(ValueError):
            partitioner.split_slice(sl, splits)

    @pytest.mark.parametrize(
        "sl, splits, sls",
        [(slice(0, 10), 2, [slice(0, 5), slice(5, 10)]),
         (slice(0, 10), 3, [slice(0, 4), slice(4, 8), slice(8, 10)]),
         ])
    def test_slice_splitting(self, sl, splits, sls):
        """Tests that slices can be split into smaller slices with evenly
        distributed numbers of atoms.
        """
        assert partitioner.split_slice(sl, splits) == sls


class TestPartitionNet(object):
    def test_replace_sinks_1_to_1(self):
        # Define objects and a replacement
        obj_a = Vertex()
        obj_b = Vertex()
        obj_c = Vertex()
        obj_d = Vertex()
        replacements = {obj_b: obj_d}

        # Create a net and ensure that it is swapped
        n = Net(obj_a, [obj_b, obj_c])
        new_n = partitioner.partition_net(n, replacements)[0]

        assert new_n.source is obj_a
        assert new_n.weight == n.weight
        assert set(new_n.sinks) == {obj_c, obj_d}

    def test_replace_sources_1_to_1(self):
        # Define objects and a replacement
        obj_a = Vertex()
        obj_b = Vertex()
        obj_d = Vertex()
        replacements = {obj_a: obj_d}

        # Create a net and ensure that it is swapped
        n = Net(obj_a, [obj_b])
        new_n = partitioner.partition_net(n, replacements)[0]

        assert new_n.source is obj_d
        assert new_n.weight == n.weight
        assert new_n.sinks == n.sinks

    def test_replace_sinks_1_to_many(self):
        # Define objects and a replacement
        obj_a = Vertex()
        obj_b = Vertex()
        obj_c = Vertex()
        obj_d = Vertex()
        obj_e = Vertex()
        replacements = {obj_b: [obj_d, obj_e]}

        # Create a net and ensure that it is swapped
        n = Net(obj_a, [obj_b, obj_c])
        new_n = partitioner.partition_net(n, replacements)[0]

        assert new_n.source is obj_a
        assert new_n.weight == n.weight
        assert set(new_n.sinks) == {obj_c, obj_d, obj_e}

    def test_replace_sources_1_to_many(self):
        # Define objects and a replacement
        obj_a = Vertex()
        obj_b = Vertex()
        obj_d = Vertex()
        obj_e = Vertex()
        replacements = {obj_a: [obj_d, obj_e]}

        # Create a net and ensure that it is swapped
        n = Net(obj_a, [obj_b])
        new_nets = partitioner.partition_net(n, replacements)

        assert len(new_nets) == 2
        for new_n in new_nets:
            assert new_n.source is obj_d or new_n.source is obj_e
            assert new_n.weight == n.weight
            assert new_n.sinks == n.sinks

    def test_replace(self):
        # Define objects and a replacement
        obj_a = Vertex()
        obj_b = Vertex()
        obj_d = Vertex()
        obj_e = Vertex()
        obj_f = Vertex()
        obj_g = Vertex()
        replacements = {obj_a: [obj_d, obj_e], obj_b: [obj_f, obj_g]}

        ks = mock.Mock()

        # Create a net and ensure that it is swapped
        n = Net(obj_a, [obj_b], keyspace=ks)
        new_nets = partitioner.partition_net(n, replacements)

        assert len(new_nets) == 2
        for new_n in new_nets:
            assert new_n.source is obj_d or new_n.source is obj_e
            assert new_n.weight == n.weight
            assert set(new_n.sinks) == {obj_f, obj_g}
            assert new_n.keyspace is ks
