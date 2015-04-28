"""Tests for BitFields.

Please note that for historical reasons, in this file instances of
:py:class:`rig.bitfield.BitField` are commonly named `ks`, standing for `Key
Space` (or variants thereof).
"""

import pytest

from six import next, itervalues

from mock import Mock

from rig.bitfield import BitField, UnavailableFieldError, UnknownTagError


class TestBitField_Tree(object):

    @pytest.fixture
    def tree(self):
        return BitField._Tree()

    def test_basic_add_remove(self, tree):
        # Should be able to add an arbitrary field to the root and get it back
        # out again
        a = Mock()
        b = Mock()
        tree.add_field(a, "a", {})
        tree.add_field(b, "b", {})
        assert tree.get_field("a", {}) is a
        assert tree.get_field("b", {}) is b

        # Should be able to get values out when values are set too
        assert tree.get_field("a", {"b": 1}) is a
        assert tree.get_field("a", {"a": 0, "b": 1}) is a

        # Shouldn't be able to get non-existant fields
        with pytest.raises(UnavailableFieldError):
            tree.get_field("nonexistant", {})

        # Should be able to add dependencies
        aa = Mock()
        ab = Mock()
        tree.add_field(aa, "aa", {"a": 0})
        tree.add_field(ab, "ab", {"a": 0})
        assert tree.get_field("aa", {"a": 0}) is aa
        assert tree.get_field("ab", {"a": 0}) is ab

        # Should not be able to get out fields when dependencies not met
        with pytest.raises(UnavailableFieldError):
            tree.get_field("aa", {})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("ab", {"a": 1})

        # Should support sharing the same name in different contexts
        aa_ = Mock()
        tree.add_field(aa_, "aa", {"a": 1})
        assert tree.get_field("aa", {"a": 0}) is aa
        assert tree.get_field("aa", {"a": 1}) is aa_

        # Should support multiple dependencies
        a_and_b = Mock()
        tree.add_field(a_and_b, "a_and_b", {"a": 2, "b": 3})
        assert tree.get_field("a_and_b", {"a": 2, "b": 3}) is a_and_b
        with pytest.raises(UnavailableFieldError):
            tree.get_field("a_and_b", {"a": 1})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("a_and_b", {"a": 2})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("a_and_b", {"b": 3})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("a_and_b", {"a": 1, "b": 3})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("a_and_b", {"a": 2, "b": 2})

        # Should support multiple levels of dependencies
        abc = Mock()
        tree.add_field(abc, "abc", {"a": 0, "aa": 1})
        assert tree.get_field("abc", {"a": 0, "aa": 1}) is abc
        assert tree.get_field("abc", {"a": 0, "aa": 1, "ab": 0}) is abc
        with pytest.raises(UnavailableFieldError):
            tree.get_field("abc", {"a": 0})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("abc", {"aa": 1})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("abc", {"a": 1, "aa": 1})
        with pytest.raises(UnavailableFieldError):
            tree.get_field("abc", {"a": 0, "aa": 0})

    def test_namespace(self, tree):
        # Make sure two things can share the same name when hidden by the
        # hierarchy
        a = Mock()
        b = Mock()
        tree.add_field(a, "a", {})
        tree.add_field(b, "b", {})

        # Should work fine!
        both_a0 = Mock()
        both_a1 = Mock()
        tree.add_field(both_a0, "both", {"a": 0})
        tree.add_field(both_a1, "both", {"a": 1})
        assert tree.get_field("both", {"a": 0}) is both_a0
        assert tree.get_field("both", {"a": 1}) is both_a1

        # Should fail when we re-use a name
        with pytest.raises(ValueError):
            tree.add_field(Mock(), "both", {"a": 1})

        # Should fail if we *could* collide higher up the hierarchy
        with pytest.raises(ValueError):
            tree.add_field(Mock(), "both", {})

    def test_get_field_requirements(self, tree):
        a = Mock()
        b = Mock()
        c = Mock()
        _ = Mock()
        __ = Mock()
        tree.add_field(_, "_", {})
        tree.add_field(__, "__", {"_": 0})
        tree.add_field(a, "a", {})
        tree.add_field(b, "b", {"a": 0})
        tree.add_field(c, "c", {"a": 0, "b": 1})

        # Should report back only relevent fields, even when others are
        # included
        assert tree.get_field_requirements("a", {}) == {}
        assert tree.get_field_requirements("a", {"_": 0}) == {}

        assert tree.get_field_requirements("b", {"a": 0}) == {"a": 0}
        assert tree.get_field_requirements("b", {"a": 0, "_": 0}) == {"a": 0}

        assert tree.get_field_requirements("c", {"a": 0, "b": 1}) ==\
            {"a": 0, "b": 1}
        assert tree.get_field_requirements("c", {"a": 0, "b": 1, "_": 0}) ==\
            {"a": 0, "b": 1}

        # Should fail if a field is blocked/does not exist
        with pytest.raises(UnavailableFieldError):
            tree.get_field_requirements("b", {"a": 1})
        with pytest.raises(UnavailableFieldError):
            tree.get_field_requirements("nonexistant", {})

    def test_get_field_candidates(self, tree):
        a = Mock()
        b = Mock()
        tree.add_field(a, "a", {})
        tree.add_field(b, "b", {})

        # Simple case: should be a single null suggestion
        assert tree.get_field_candidates("a", {}) == [{}]

        both_a0 = Mock()
        both_a1 = Mock()
        tree.add_field(both_a0, "both", {"a": 0})
        tree.add_field(both_a1, "both", {"a": 1})

        # Ambiguous case: should be two suggestions
        assert tree.get_field_candidates("both", {}) == [{"a": 0}, {"a": 1}]

        ab = Mock()
        tree.add_field(ab, "ab", {"a": 0, "b": 1})

        # Nested case
        assert tree.get_field_candidates("ab", {}) == [{"a": 0, "b": 1}]

        # Partially specified cases
        assert tree.get_field_candidates("ab", {"a": 0}) == [{"b": 1}]
        assert tree.get_field_candidates("ab", {"b": 1}) == [{"a": 0}]

        # Conflicted candidates blocks suggestion
        assert tree.get_field_candidates("ab", {"a": 2}) == []

    def test_get_field_human_readable(self, tree):
        tree.add_field(Mock(), "a", {})
        tree.add_field(Mock(), "b", {})
        tree.add_field(Mock(), "c", {"a": 0})
        tree.add_field(Mock(), "d", {"a": 0, "b": 1})

        # Just reports the name of fields which don't have any field
        # value requirements.
        assert tree.get_field_human_readable("a", {}) == "'a'"
        assert tree.get_field_human_readable("a", {"a": 0, "b": 1}) == "'a'"

        # Prints field value requirements when present
        assert tree.get_field_human_readable("c", {"a": 0}) == "'c' ('a':0)"
        assert tree.get_field_human_readable("c", {"a": 0, "b": 1}) ==\
            "'c' ('a':0)"

        # Prints field value with multiple requirements (in creation order)
        # when present
        assert tree.get_field_human_readable("d", {"a": 0, "b": 1}) ==\
            "'d' ('a':0, 'b':1)"

    def test_enabled_fields(self, tree):
        a = Mock()
        aa = Mock()
        b = Mock()
        bb = Mock()
        tree.add_field(a, "a", {})
        tree.add_field(aa, "aa", {"a": 0})
        tree.add_field(b, "b", {})
        tree.add_field(bb, "bb", {"b": 1})

        assert list(tree.enabled_fields({})) == [("a", a), ("b", b)]

        assert list(tree.enabled_fields({"a": 0})) ==\
            [("a", a), ("b", b), ("aa", aa)]
        assert list(tree.enabled_fields({"a": 1})) == [("a", a), ("b", b)]

        assert list(tree.enabled_fields({"b": 1})) ==\
            [("a", a), ("b", b), ("bb", bb)]
        assert list(tree.enabled_fields({"b": 0})) == [("a", a), ("b", b)]

        assert list(tree.enabled_fields({"a": 0, "b": 1})) ==\
            [("a", a), ("b", b), ("aa", aa), ("bb", bb)]

    def test_potential_fields(self, tree):
        a = Mock()
        aa = Mock()
        aaa = Mock()
        b = Mock()
        bb = Mock()
        tree.add_field(a, "a", {})
        tree.add_field(aa, "aa", {"a": 0})
        tree.add_field(aaa, "aaa", {"a": 0, "aa": 1})
        tree.add_field(b, "b", {})
        tree.add_field(bb, "bb", {"b": 2})

        # All fields initially visible
        assert list(tree.potential_fields({})) ==\
            [("a", a), ("b", b), ("aa", aa), ("aaa", aaa), ("bb", bb)]

        # Selecting things doesn't remove anything
        assert list(tree.potential_fields({"a": 0})) ==\
            [("a", a), ("b", b), ("aa", aa), ("aaa", aaa), ("bb", bb)]
        assert list(tree.potential_fields({"b": 2})) ==\
            [("a", a), ("b", b), ("aa", aa), ("aaa", aaa), ("bb", bb)]
        assert list(tree.potential_fields({"a": 0, "b": 2})) ==\
            [("a", a), ("b", b), ("aa", aa), ("aaa", aaa), ("bb", bb)]
        assert list(tree.potential_fields({"a": 0, "aa": 1, "b": 2})) ==\
            [("a", a), ("b", b), ("aa", aa), ("aaa", aaa), ("bb", bb)]

        # Blocking things removes the offending elements, recursively
        assert list(tree.potential_fields({"a": 1})) ==\
            [("a", a), ("b", b), ("bb", bb)]
        assert list(tree.potential_fields({"b": 3})) ==\
            [("a", a), ("b", b), ("aa", aa), ("aaa", aaa)]


class TestBitFieldAddField(object):
    @pytest.fixture
    def ks(self):
        return BitField(64)

    @pytest.mark.parametrize("start_at, length", [(64, None), (128, None),
                                                  (63, 2), (128, 2)])
    def test_fixed_fields_beyond_length(self, ks, start_at, length):
        # Assert that we can't create a new bit field with fixed fields beyond
        # its length
        with pytest.raises(ValueError):
            ks.add_field("out_of_range", start_at=start_at, length=length)

    def test_nonzero_lengths(self, ks):
        # Check fields must have non-zero lengths
        with pytest.raises(ValueError):
            ks.add_field("zero_length", length=0, start_at=0)

    @pytest.mark.parametrize("length, start_at",
                             [(8, 8), (16, 0), (12, 0), (16, 8), (12, 12),
                              (4, 10)])
    def test_non_overlapping(self, ks, start_at, length):
        # Check we can't create overlapping fixed fields
        ks.add_field("obstruction", length=8, start_at=8)
        with pytest.raises(ValueError):
            ks.add_field("obstructed", length=length, start_at=start_at)

    def test_unique_identifiers(self, ks):
        # Check we can't create fields with the same name but which otherwise
        # don't clash
        ks.add_field("obstruction", length=8, start_at=8)
        with pytest.raises(ValueError):
            ks.add_field("obstruction", length=1, start_at=0)

    def test_namespaces(self, ks):
        ks.add_field("top")
        ks_top0 = ks(top=0)
        ks_top1 = ks(top=1)

        # Should not be able to blatently re-use names.
        with pytest.raises(ValueError):
            ks.add_field("top")

        # Should be able to re-use names further down the hierarchy
        ks_top0.add_field("a")
        ks_top1.add_field("a")

        # Should not be able to re-use names of parents.
        with pytest.raises(ValueError):
            ks_top0.add_field("top")

        # Should not be able to re-use names of indirect parents.
        ks_top0_a0 = ks_top0(a=1)
        with pytest.raises(ValueError):
            ks_top0_a0.add_field("top")

        # Should be blocked from using names which are used further down the
        # hierarchy.
        with pytest.raises(ValueError):
            ks.add_field("a")

        # Should be blocked even when further down some other part of the
        # hierarchy (which requires searching higher up the hierarchy)
        ks.add_field("other")
        ks_other0 = ks(other=0)
        with pytest.raises(ValueError):
            ks_other0.add_field("a")


def test_bitfield_masks():
    # Create a new bit field and check that appropriate masks can be retrieved
    # from it, filtering by tag.
    ks = BitField(64)
    ks.add_field("bottom", length=32, start_at=0, tags="Bottom All")
    ks.add_field("top", length=8, start_at=56, tags="Top All")

    # Test universal access
    assert ks.get_mask() == 0xFF000000FFFFFFFF

    # Test field-name access
    assert ks.get_mask(field="bottom") == 0x00000000FFFFFFFF
    assert ks.get_mask(field="top") == 0xFF00000000000000

    # Test tag access
    assert ks.get_mask(tag="All") == 0xFF000000FFFFFFFF
    assert ks.get_mask(tag="Bottom") == 0x00000000FFFFFFFF
    assert ks.get_mask(tag="Top") == 0xFF00000000000000

    # Test both at once fails
    with pytest.raises(TypeError):
        ks.get_mask(tag="All", field="top")


def test_bitfield_keys():
    # Create a new bit field and check that keys can be filled in and extracted
    ks = BitField(32)
    ks.add_field("a", length=8, start_at=0, tags="A All")
    ks.add_field("b", length=8, start_at=8, tags="B All")
    ks.add_field("c", length=8, start_at=16, tags="C All")

    # Shouldn't be able to access a field which isn't defined
    with pytest.raises(UnavailableFieldError):
        ks.d

    # Shouldn't be able to set a field which isn't defined
    with pytest.raises(UnavailableFieldError):
        ks(d=123)

    # Shouldn't be able to get values before they're assigned
    with pytest.raises(ValueError):
        ks.get_value()
    with pytest.raises(ValueError):
        ks.get_value(tag="All")
    with pytest.raises(ValueError):
        ks.get_value(field="a")
    with pytest.raises(ValueError):
        ks.get_value(tag="A")
    with pytest.raises(ValueError):
        ks.get_value(field="b")
    with pytest.raises(ValueError):
        ks.get_value(tag="B")
    with pytest.raises(ValueError):
        ks.get_value(field="c")
    with pytest.raises(ValueError):
        ks.get_value(tag="C")

    # Should just get None for unspecified fields
    assert ks.a is None
    assert ks.b is None
    assert ks.c is None

    # Shouldn't be able to set value out of range
    with pytest.raises(ValueError):
        ks_a = ks(a=0x100)
    with pytest.raises(ValueError):
        ks_a = ks(a=-1)

    # Set a field, should now be able to get that field but not others
    ks_a = ks(a=0xAA)
    assert ks_a.a == 0xAA
    assert ks_a.b is None
    assert ks_a.c is None
    assert ks_a.get_value(field="a") == 0x000000AA
    assert ks_a.get_value(tag="A") == 0x000000AA
    with pytest.raises(ValueError):
        ks_a.get_value()
    with pytest.raises(ValueError):
        ks_a.get_value(tag="All")
    with pytest.raises(ValueError):
        ks_a.get_value(field="b")
    with pytest.raises(ValueError):
        ks_a.get_value(tag="B")
    with pytest.raises(ValueError):
        ks_a.get_value(field="c")
    with pytest.raises(ValueError):
        ks_a.get_value(tag="C")

    # Should not be able to change a field
    with pytest.raises(ValueError):
        ks_a(a=0x00)
    with pytest.raises(ValueError):
        ks_a(a=0xAA)

    # Fill in all fields, everything should now drop out
    ks_abc = ks_a(b=0xBB, c=0xCC)
    assert ks_abc.a == 0xAA
    assert ks_abc.b == 0xBB
    assert ks_abc.c == 0xCC
    assert ks_abc.get_value() == 0x00CCBBAA
    assert ks_abc.get_value(field="a") == 0x000000AA
    assert ks_abc.get_value(field="b") == 0x0000BB00
    assert ks_abc.get_value(field="c") == 0x00CC0000
    assert ks_abc.get_value(tag="All") == 0x00CCBBAA
    assert ks_abc.get_value(tag="A") == 0x000000AA
    assert ks_abc.get_value(tag="B") == 0x0000BB00
    assert ks_abc.get_value(tag="C") == 0x00CC0000

    # Test some special-case values
    ks_a0 = ks(a=0)
    assert ks_a0.get_value(field="a") == 0x00000000
    ks_a1 = ks(a=1)
    assert ks_a1.get_value(field="a") == 0x00000001
    ks_aFF = ks(a=0xFF)
    assert ks_aFF.get_value(field="a") == 0x000000FF


def test_bitfield_tags():
    # Test the ability to define tags in different ways
    ks = BitField(6)
    ks.add_field("a", length=1, start_at=0)
    ks.add_field("b", length=1, start_at=1, tags="B")
    ks.add_field("c", length=1, start_at=2, tags="C C_")
    ks.add_field("d", length=1, start_at=3, tags=["D"])
    ks.add_field("e", length=1, start_at=4, tags=["E", "E_"])

    assert ks.get_tags("a") == set()
    assert ks.get_tags("b") == set(["B"])
    assert ks.get_tags("c") == set(["C", "C_"])
    assert ks.get_tags("d") == set(["D"])
    assert ks.get_tags("e") == set(["E", "E_"])

    ks_def = ks(a=1, b=1, c=1, d=1, e=1)
    assert ks_def.get_mask() == 0x1F
    assert ks_def.get_mask("B") == 0x02
    assert ks_def.get_mask("C") == 0x04
    assert ks_def.get_mask("C_") == 0x04
    assert ks_def.get_mask("D") == 0x08
    assert ks_def.get_mask("E") == 0x10
    assert ks_def.get_mask("E_") == 0x10

    # Test that non-existant tags cause an error
    with pytest.raises(UnknownTagError):
        ks.get_mask("Non-existant")
    with pytest.raises(UnknownTagError):
        ks.get_value("Non-existant")

    assert ks_def.get_value() == 0x1F
    assert ks_def.get_value("B") == 0x02
    assert ks_def.get_value("C") == 0x04
    assert ks_def.get_value("C_") == 0x04
    assert ks_def.get_value("D") == 0x08
    assert ks_def.get_value("E") == 0x10
    assert ks_def.get_value("E_") == 0x10

    ks_a0 = ks(a=0)
    ks_a0.add_field("a0", length=1, start_at=5, tags="A0")
    ks_a1 = ks(a=1)
    ks_a1.add_field("a1", length=1, start_at=5, tags="A1")

    # Test that tags are applied heirachically to parents
    assert ks.get_tags("a") == set(["A0", "A1"])
    assert ks_a0.get_tags("a0") == set(["A0"])
    assert ks_a1.get_tags("a1") == set(["A1"])
    assert ks.get_mask("A0") == 0x01
    assert ks.get_mask("A1") == 0x01

    # Test that fields become available when selected
    assert ks_a0.get_mask("A0") == 0b100001
    assert ks_a0(a0=1).get_value("A0") == 0b100000
    assert ks.get_mask("A1") == 0x01

    assert ks_a1.get_mask("A1") == 0b100001
    assert ks_a1(a1=1).get_value("A1") == 0b100001
    assert ks.get_mask("A0") == 0x01


def test_bitfield_hierarchy():
    ks = BitField(8)
    ks.add_field("always", length=1, start_at=7)
    ks.add_field("split", length=1, start_at=6)

    # Add different fields dependent on the split-bit. This checks that
    # creating fields in different branches of the hierarchy doesn't result in
    # clashes.  Additionally creates multiple levels of hierarchy.
    ks_s0 = ks(split=0)
    ks_s0.add_field("s0_btm", length=3, start_at=0)
    ks_s0.add_field("s0_top", length=3, start_at=3)

    ks_s1 = ks(split=1)
    ks_s1.add_field("s1_btm", length=2, start_at=0)
    ks_s1.add_field("s1_top", length=2, start_at=2)
    ks_s1s = ks_s1(s1_btm=0, s1_top=0)
    ks_s1s.add_field("split2", length=2, start_at=4)

    # Shouldn't be able to access child-fields of split before it is defined
    with pytest.raises(UnavailableFieldError):
        ks.s0_top
    with pytest.raises(UnavailableFieldError):
        ks.s0_btm
    with pytest.raises(UnavailableFieldError):
        ks.s1_top
    with pytest.raises(UnavailableFieldError):
        ks.s1_btm
    with pytest.raises(UnavailableFieldError):
        ks.split2

    # Should be able to define a new key from scratch
    ks_s0_defined = ks(always=1, split=0, s0_btm=3, s0_top=5)
    assert ks_s0_defined.always == 1
    assert ks_s0_defined.split == 0
    assert ks_s0_defined.s0_btm == 3
    assert ks_s0_defined.s0_top == 5
    assert ks_s0_defined.get_value() == 0b10101011
    assert ks_s0_defined.get_mask() == 0b11111111

    # Should be able to order child keys before the parent key too in the
    # arguments without causing a crash
    ks(s0_btm=3, s0_top=5, always=1, split=0)

    # Accessing fields from the other side of the split should fail
    with pytest.raises(UnavailableFieldError):
        ks_s0_defined.s1_btm
    with pytest.raises(UnavailableFieldError):
        ks_s0_defined.s1_top
    with pytest.raises(UnavailableFieldError):
        ks_s0_defined.split2

    # Shouldn't have to define all top-level fields in order to get at split
    # fields
    ks_s1_selected = ks(split=1)
    assert ks_s1_selected.split == 1
    assert ks_s1_selected.always is None
    assert ks_s1_selected.s1_btm is None
    assert ks_s1_selected.s1_top is None

    # Accessing fields from the other side of the split should still fail
    with pytest.raises(UnavailableFieldError):
        ks_s1_selected.s0_btm
    with pytest.raises(UnavailableFieldError):
        ks_s1_selected.s0_top

    # Accessing fields in a split lower in the hierarchy should still fail
    with pytest.raises(UnavailableFieldError):
        ks_s1_selected.split2

    # Should be able to access the second-level of split
    ks_s1s_selected = ks(always=1, split=1, s1_btm=0, s1_top=0, split2=3)
    assert ks_s1s_selected.always == 1
    assert ks_s1s_selected.split == 1
    assert ks_s1s_selected.s1_btm == 0
    assert ks_s1s_selected.s1_top == 0
    assert ks_s1s_selected.split2 == 3

    # Should not be able to set child fields before parent field is set
    with pytest.raises(UnavailableFieldError):
        ks(s0_btm=3, s0_top=5)


def test_hierarchy_subfield_obstructions():
    # Test that if a subfield blocks a space, another field cannot be added
    # there at a higher level in the hierarchy
    ks_obst = BitField(32)
    ks_obst.add_field("split")
    ks_obst_s1 = ks_obst(split=1)
    ks_obst_s1.add_field("obstruction", start_at=0)
    with pytest.raises(ValueError):
        ks_obst.add_field("obstructed", start_at=0)

    # And that such a field does not get auto-positioned there
    ks_obst.add_field("obstructed")
    ks_obst.assign_fields()
    assert ks_obst_s1.get_mask(field="obstruction") == 0x00000001
    assert ks_obst.get_mask(field="split") == 0x00000002
    assert ks_obst.get_mask(field="obstructed") == 0x00000004


def test_auto_length():
    # Tests for automatic length calculation.
    # Test that fields never given any values just become single-bit fields
    ks_never = BitField(8)
    ks_never.add_field("never", start_at=0)
    ks_never.assign_fields()
    assert ks_never.get_mask() == 0x01

    # Test that we can't start an auto-length field within an existing field.
    with pytest.raises(ValueError):
        ks_never.add_field("obstructed", start_at=0)

    # Make sure that assign_fields() also forces a fixing of the size
    ks_once = BitField(8)
    ks_once.add_field("once", start_at=0)
    once_fifteen = ks_once(once=0x0F)
    with pytest.raises(ValueError):
        ks_once.get_mask()
    with pytest.raises(ValueError):
        once_fifteen.get_value()
    ks_once.assign_fields()
    assert once_fifteen.get_value() == 0x0F
    assert once_fifteen.get_mask() == 0x0F

    # The signle-bit value should happily fit only 0 and 1
    assert ks_never(never=0).never == 0
    assert ks_never(never=1).never == 1
    with pytest.raises(ValueError):
        ks_never(never=2)

    # Test that fields can be sized automatically but positioned manually
    ks = BitField(64)
    ks.add_field("auto_length", start_at=32)

    # Create a load of keys (of which one is at least 32-bits long)
    for val in [0, 1, 0xDEADBEEF, 0x1234]:
        ks_val = ks(auto_length=val)
        assert ks_val.auto_length == val

    # The resulting field should be 32 bits long
    ks.assign_fields()
    assert ks.get_mask() == 0xFFFFFFFF00000000

    # The field's length should now be fixed
    with pytest.raises(ValueError):
        ks(auto_length=0x100000000)

    # Test that fields can be created which, when auto-lengthed after a large
    # field value, don't fit.
    ks_long = BitField(16)
    ks_long.add_field("too_long", start_at=0)
    ks_long(too_long=0x10000)
    with pytest.raises(ValueError):
        ks_long.assign_fields()

    # Unfixed field should render the mask inaccessible
    with pytest.raises(ValueError):
        ks_long.get_mask()

    # Test that fields can be generated hierarchically
    ks_h = BitField(16)
    ks_h.add_field("split", start_at=8)
    ks_h_s0 = ks_h(split=0)
    ks_h_s0.add_field("s0", start_at=0)
    ks_h_s2 = ks_h(split=2)
    ks_h_s2.add_field("s2", start_at=0)

    # Test that after assigning fields, the field sizes become fixed on both
    # sides (even if the assign_fields call occurs on one side of the split)
    ks_h_s0_val = ks_h(split=0, s0=0x10)
    ks_h_s0_val.assign_fields()
    assert ks_h_s0_val.get_mask() == 0x031F
    assert ks_h_s0_val.get_value() == 0x0010

    # Make sure this side and the split field are now fixed
    with pytest.raises(ValueError):
        ks_h(split=0, s0=0x3F)
    with pytest.raises(ValueError):
        ks_h(split=4)

    # Make sure the other side of the split is also fixed (this will raise an
    # exception if it has been fixed since its size would be fixed as 1 as no
    # values have been assigned to it).
    with pytest.raises(ValueError):
        ks_h(split=2, s2=0x3F)


def test_auto_start_at():
    # Test automatic positioning of fixed-length fields
    ks = BitField(32)

    ks.add_field("a", length=4)
    ks.add_field("b", length=4)
    ks.add_field("c", length=4)

    # Shouldn't be able to get keys/masks before field positions assigned
    with pytest.raises(ValueError):
        ks.get_mask()
    with pytest.raises(ValueError):
        ks(a=0).get_value(field="a")

    ks.assign_fields()

    # Test that all fields are allocated at once and in order of insertion
    assert ks.get_mask(field="c") == 0x00000F00
    assert ks.get_mask(field="b") == 0x000000F0
    assert ks.get_mask(field="a") == 0x0000000F
    assert ks.get_mask() == 0x00000FFF

    # Test positioning when a space is fully obstructed
    ks.add_field("full_obstruction", length=4, start_at=12)
    ks.add_field("d", length=4)
    ks.assign_fields()
    assert ks.get_mask(field="d") == 0x000F0000

    # Test positioning when a space is partially obstructed. The first field
    # will end up after the second field since the second field can fill the
    # gap left by the partial obstruction.
    ks.add_field("partial_obstruction", length=4, start_at=22)
    ks.add_field("e", length=4)
    ks.add_field("f", length=2)
    ks.assign_fields()
    assert ks.get_mask(field="e") == 0x3C000000
    assert ks.get_mask(field="f") == 0x00300000

    # Ensure we can define fields which don't fit when placed
    ks.add_field("last_straw", length=4)
    with pytest.raises(ValueError):
        ks.assign_fields()


def test_auto_start_at_hierarchy():
    # Test that auto-placed fields can be created hierarchically
    ks_h = BitField(32)
    ks_h.add_field("split", length=4)

    # Ensure that additional top-level fields are placed after all split
    # fields.
    ks_h.add_field("always_before", length=4)

    ks_h_s0 = ks_h(split=0)
    ks_h_s0.add_field("s0", length=4)
    ks_h_s1 = ks_h(split=1)
    ks_h_s1.add_field("s1", length=8)

    # Check that assigning fields on one side of the split fixes all fields
    ks_h(split=0).assign_fields()
    assert ks_h(split=0).get_mask(field="s0") == 0x0000000F
    assert ks_h(split=0).get_mask(field="split") == 0x00000F00
    assert ks_h(split=0).get_mask(field="always_before") == 0x0000F000
    assert ks_h(split=0).get_mask() == 0x0000FF0F
    with pytest.raises(ValueError):
        ks_h_s0.add_field("obstructed", start_at=8)

    assert (ks_h(split=1).get_mask(field="split") ==
            ks_h(split=0).get_mask(field="split"))
    assert (ks_h(split=1).get_mask(field="always_before") ==
            ks_h(split=0).get_mask(field="always_before"))
    assert ks_h(split=1).get_mask(field="s1") == 0x000000FF
    assert ks_h(split=1).get_mask() == 0x0000FFFF
    with pytest.raises(ValueError):
        ks_h_s1.add_field("obstructed", length=4, start_at=8)


def test_mix_auto_length_fixed_start():
    """Test that we can specify a field with no set length and a fixed start
    position and that this can't be overwritten by another fully auto field.
    """
    ks = BitField(32)
    ks.add_field("a")
    ks.add_field("b", start_at=0)

    # Give the fields values to force their sizes
    ks(a=0xFF, b=0xFFF)

    # Check the masks come out correctly
    ks.assign_fields()
    assert ks.get_mask(field="a") == 0x000FF000
    assert ks.get_mask(field="b") == 0x00000FFF
    assert ks.get_mask() == 0x000FFFFF


def test_mix_auto_length_fixed_start_hierarchy():
    ks = BitField(32)
    ks.add_field("s")

    ks_0 = ks(s=0)
    ks_0.add_field("s0", length=4, start_at=0)

    ks_1 = ks(s=1)
    ks_1.add_field("s1", length=8, start_at=0)

    ks.assign_fields()
    assert ks_0.get_mask(field="s0") == 0x0000000f
    assert ks_1.get_mask(field="s1") == 0x000000ff
    assert ks.get_mask(field="s") == 0x00000100


def test_mix_auto_length_fixed_start_impossible():
    """Test that overlapping fixed starts with auto lengths fail."""
    ks = BitField(32)
    ks.add_field("a", start_at=0)
    ks.add_field("b", start_at=1)

    # Give the fields values to force their sizes, a and b now overlap
    ks(a=0xFF, b=0xFFF)

    # Check that this is impossible
    with pytest.raises(ValueError):
        ks.assign_fields()


class TestFullAuto(object):
    def test_placement_and_length(self):
        # Brief test that automatic placement and length assignment can happen
        # simultaneously
        ks = BitField(32)
        ks.add_field("a")
        ks.add_field("b")

        # Give the fields values to force their sizes
        ks(a=0xFF, b=0xFFF)

        # Check the masks come out correctly
        ks.assign_fields()
        assert ks.get_mask(field="a") == 0x000000FF
        assert ks.get_mask(field="b") == 0x000FFF00
        assert ks.get_mask() == 0x000FFFFF

    def test_with_hierarchy(self):
        # Also test that assignment of fields works at multiple levels of
        # hierarchy
        ks_h = BitField(32)
        ks_h.add_field("s")

        ks_h(s=0).add_field("s0")
        ks_h(s=0, s0=0).add_field("s00")
        ks_h(s=0, s0=1).add_field("s01")

        ks_h(s=1).add_field("s1")
        ks_h(s=1, s1=0).add_field("s10")
        ks_h(s=1, s1=1).add_field("s11")

        ks_h.assign_fields()

        assert ks_h.get_mask(field="s") == 0x00000004
        assert ks_h(s=0).get_mask(field="s0") == 0x00000002
        assert ks_h(s=1).get_mask(field="s1") == 0x00000002
        assert ks_h(s=0, s0=0).get_mask(field="s00") == 0x00000001
        assert ks_h(s=0, s0=1).get_mask(field="s01") == 0x00000001
        assert ks_h(s=1, s1=0).get_mask(field="s10") == 0x00000001
        assert ks_h(s=1, s1=1).get_mask(field="s11") == 0x00000001


def test_eq():
    # Check that two bit fields with the same fields and values (but defined
    # seperately) are not equivilent.
    ks1 = BitField(32)
    ks2 = BitField(32)
    assert ks1 != ks2

    ks1.add_field("test", length=2, start_at=1)
    ks2.add_field("test", length=2, start_at=1)
    assert ks1 != ks2

    ks1_val = ks1(test=1)
    ks2_val = ks2(test=1)
    assert ks1_val != ks2_val

    # And that they're still different when completely different fields/values
    # are given
    ks1.add_field("test1", length=10, start_at=20)
    ks2.add_field("test2", length=20, start_at=10)
    assert ks1 != ks2

    ks1_val2 = ks1(test1=10)
    ks2_val2 = ks2(test2=20)
    assert ks1_val2 != ks2_val2

    # Check self-equivilence, even with fields and values set
    ks = BitField(32)
    assert ks == ks

    ks.add_field("test")
    ks.add_field("split")

    ks_s0 = ks(split=0)
    ks_s0.add_field("s0")
    ks_s1 = ks(split=1)
    ks_s1.add_field("s1")

    assert ks == ks

    ks_val0 = ks(test=0, split=1, s1=2)
    ks_val1 = ks(test=0)(split=1, s1=2)
    ks_val2 = ks(test=0, split=1)(s1=2)
    ks_val3 = ks(test=0)(split=1)(s1=2)

    assert ks_val0 == ks_val1 == ks_val2 == ks_val3

    # Check inequality when values do differ
    assert ks != ks_val0

    ks_val_diff = ks(test=123)
    assert ks_val_diff != ks_val0


def test_repr():
    # Very rough tests to ensure the string representation of a bit field is
    # reasonably sane.
    ks = BitField(128)
    ks.add_field("always")
    ks.add_field("split")
    ks_s0 = ks(split=0)
    ks_s0.add_field("s0")
    ks_s1 = ks(split=1)
    ks_s1.add_field("s1")

    # Basic info should appear
    assert "128" in repr(ks)
    assert "BitField" in repr(ks)

    # Global fields should appear, even if undefined
    assert "'always'" in repr(ks)
    assert "'split'" in repr(ks)

    # Values should appear when defined
    assert "12345" in repr(ks(always=12345))

    # Fields behind splits should not be shown if the split field is not
    # defined
    assert "'s0'" not in repr(ks)
    assert "'s1'" not in repr(ks)

    # Fields should be shown when split is defined accordingly
    assert "'s0'" in repr(ks_s0)
    assert "'s1'" not in repr(ks_s0)
    assert "'s0'" not in repr(ks_s1)
    assert "'s1'" in repr(ks_s1)


def test_subclass():
    """It should be possible to inherit from BitField and still have __call__
    and internal type-overriding work.
    """
    class MyBitField(BitField):

        class _Tree(BitField._Tree):
            pass

        class _Field(BitField._Field):
            pass

        pass

    x = MyBitField()
    x.add_field("spam")
    x(spam=1).add_field("eggs")

    # Make sure __call__ works
    y = x(spam=0)
    assert isinstance(y, MyBitField)

    # Make sure tree type is overridden
    assert type(x.fields) is MyBitField._Tree
    assert type(next(itervalues(x.fields.children))) is MyBitField._Tree

    # Make sure field type is overridden
    assert type(x.fields.get_field("eggs", {"spam": 1})) is MyBitField._Field
