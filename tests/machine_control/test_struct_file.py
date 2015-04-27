import pytest

from rig.machine_control.struct_file import (read_struct_file,
                                             read_conf_file, num,
                                             Struct, StructField)


@pytest.mark.parametrize(
    "s, val",
    [(b"10", 10),
     (b"0x3a", 0x3a),
     ])
def test_num(s, val):
    assert num(s) == val


no_size = b"""
# ------
name = struct_1
base = 0x7fffe

field    C    0x00    %04x    0   # Comment

# -------
name = struct_2
"""


no_size_after = b"""
# ------
name = struct_1
base = 0x7fffe

field    C    0x00    %04x    0   # Comment
"""


no_base = b"""
# ------
name = struct_1
size = 256

field    C    0x00    %04x    0   # Comment

# -------
name = struct_2
"""


no_base_after = b"""
# ------
name = struct_1
size = 256

field    C    0x00    %04x    0   # Comment
"""


neither_size_base = b"""
# ------
name = struct_1

field    v    0x00    %04x    0   # Comment

# -------
name = struct_2
"""


@pytest.mark.parametrize(
    "data, reason",
    [(no_size, "size"),
     (no_size_after, "size"),
     (no_base, "base"),
     (no_base_after, "base"),
     (neither_size_base, "size")])
def test_missing_sections(data, reason):
    with pytest.raises(ValueError) as excinfo:
        read_struct_file(data)
    assert reason in str(excinfo.value)


invalid_field = b"""
eggs = spam
"""


@pytest.mark.parametrize("data, reason", [(invalid_field, "eggs")])
def test_invalid_field_name(data, reason):
    with pytest.raises(ValueError) as excinfo:
        read_struct_file(data)
    assert reason in str(excinfo.value)


invalid_syntax = b"""\
name = test
size = 0x00
base = 0x00

x 1 2 3
"""


@pytest.mark.parametrize("data", [(invalid_syntax)])
def test_invalid_syntax(data):
    with pytest.raises(ValueError) as excinfo:
        read_struct_file(data)
    assert "syntax" in str(excinfo.value)
    assert "line 4" in str(excinfo.value)


valid = b"""
# ----
name = sv
size = 256
base = 0x345

# Name   Perl struct pack   Offset    printf    default    comment
spam     c                  0x00      %c        0          # Test
eggs     V                  0x0A      %d        4          # Test

# ---
name = sd
size = 128
base = 0

arthur[16]   A16                0x00      %f        0          # Test
"""


@pytest.mark.parametrize("data", [valid])
def test_valid_data(data):
    # Read the struct data
    structs = read_struct_file(data)

    # Check the names are present
    assert b"sv" in structs
    sv = structs[b"sv"]
    assert sv.base == 0x345
    assert sv.size == 256

    assert b"sd" in structs
    sd = structs[b"sd"]
    assert sd.base == 0
    assert sd.size == 128

    # Check the fields are sensible
    assert b"spam" in sv
    spam = sv[b"spam"]
    assert spam.pack_chars == b"b"
    assert spam.offset == 0
    assert spam.printf == b"%c"
    assert spam.default == 0
    assert spam.length == 1

    assert b"eggs" in sv
    eggs = sv[b"eggs"]
    assert eggs.pack_chars == b"I"
    assert eggs.offset == 0x0a
    assert eggs.printf == b"%d"
    assert eggs.default == 4
    assert eggs.length == 1

    assert b"arthur" in sd
    arthur = sd[b"arthur"]
    assert arthur.pack_chars == b"16s"
    assert arthur.offset == 0
    assert arthur.length == 16


conf_file = b"""
spam    0xab
eggs    44
"""

bad_conf_file_a = b"""
field_with_no_value
"""

bad_conf_file_b = b"""
field_with_badly_formatted_value   oops
"""


@pytest.mark.parametrize("data", [conf_file])
def test_read_conf_file(data):
    # Read the conf file, should return a dictionary mapping key to default
    # value.
    conf = read_conf_file(data)
    assert len(conf) == 2
    assert conf[b"spam"] == 0xab
    assert conf[b"eggs"] == 44


@pytest.mark.parametrize("data", [bad_conf_file_a, bad_conf_file_b])
def test_read_conf_file_fails(data):
    # Read the conf file, should return a dictionary mapping key to default
    # value.
    with pytest.raises(ValueError) as excinfo:
        read_conf_file(data)
    assert "syntax error" in str(excinfo.value)


class TestStruct(object):
    def test_update_default_values(self):
        """Create a simple struct object, with one field."""
        s = Struct("test")
        s[b"field"] = StructField("I", 0x00, "%d", 0xFFFF, 1)

        # Test that we can update this field correctly
        assert s[b"field"].default == 0xFFFF
        s.update_default_values(field=0xABAB)
        assert s[b"field"].default == 0xABAB

        # Test that trying to update a non-existent field fails
        with pytest.raises(KeyError) as excinfo:
            s.update_default_values(non_existent=0xff)
        assert "non_existent" in str(excinfo.value)

    def test_pack(self):
        """Test packing a struct into bytes."""
        s = Struct("test", size=6)
        s["a"] = StructField(b"I", 0x00, "%d", 0xABCDCAFE, 1)
        s["b"] = StructField(b"H", 0x04, "%d", 0xA0B1, 1)

        # This SHOULD be little-endian because the boot data is put together by
        # a little-endian machine.
        assert s.pack() == b"\xFE\xCA\xCD\xAB\xB1\xA0"
