import pytest
import tempfile

from rig.machine_control.struct_file import read_struct_file, num


@pytest.mark.parametrize(
    "s, val",
    [(b"10", 10),
     (b"0x3a", 0x3a),
     ])
def test_num(s, val):
    assert num(s) == val


@pytest.fixture
def temp_struct_file(data):
    """Writes the test data into a temporary file to be tested against.
    """
    # Create the temporary file and write in the data
    fp = tempfile.TemporaryFile()
    fp.write(data)

    # Seek to the start and return
    fp.seek(0)
    return fp


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
def test_missing_sections(temp_struct_file, reason):
    with pytest.raises(ValueError) as excinfo:
        read_struct_file(temp_struct_file)
    assert reason in str(excinfo.value)


invalid_field = b"""
eggs = spam
"""


@pytest.mark.parametrize("data, reason", [(invalid_field, "eggs")])
def test_invalid_field_name(temp_struct_file, reason):
    with pytest.raises(ValueError) as excinfo:
        read_struct_file(temp_struct_file)
    assert reason in str(excinfo.value)


invalid_syntax = b"""\
name = test
size = 0x00
base = 0x00

x 1 2 3
"""


@pytest.mark.parametrize("data", [(invalid_syntax)])
def test_invalid_syntax(temp_struct_file):
    with pytest.raises(ValueError) as excinfo:
        read_struct_file(temp_struct_file)
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
def test_valid_data(temp_struct_file):
    # Read the struct data
    structs = read_struct_file(temp_struct_file)

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
