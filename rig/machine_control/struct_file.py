"""Read struct files for SARK/SC&MP.
"""
import collections
import re
import six
import struct


def read_struct_file(struct_data):
    """Interpret a struct file defining the location of variables in memory.

    Parameters
    ----------
    struct_data : :py:class:`bytes`
        String of :py:class:`bytes` containing data to interpret as the struct
        definition.

    Returns
    -------
    {struct_name: :py:class:`~.Struct`}
        A dictionary mapping the struct name to a :py:class:`~.Struct`
        instance. **Note:** the struct name will be a string of bytes, e.g.,
        `b"vcpu"`.
    """
    # Holders for all structs
    structs = dict()

    # Holders for the current struct
    name = None

    # Iterate over every line in the file
    for i, l in enumerate(struct_data.splitlines()):
        # Empty the line of comments, if the line is empty then skip to the
        # next line.  Split on whitespace to get the tokens.
        tokens = re_comment.sub(b"", l).strip().split()
        if len(tokens) == 0:
            continue
        elif len(tokens) == 3:
            # 3 tokens implies header data
            (key, _, value) = tokens

            if key == b"name":
                if name is not None:
                    if structs[name].size is None:
                        raise ValueError(
                            "size value missing for struct '{}'".format(name))
                    if structs[name].base is None:
                        raise ValueError(
                            "base value missing for struct '{}'".format(name))
                name = value
                structs[name] = Struct(name)
            elif key == b"size":
                structs[name].size = num(value)
            elif key == b"base":
                structs[name].base = num(value)
            else:
                raise ValueError(key)
        elif len(tokens) == 5:
            # 5 tokens implies entry in struct.
            (field, pack, offset, printf, default) = tokens

            # Convert the packing character from Perl to Python standard
            num_pack = re_numbered_pack.match(pack)
            if num_pack is not None:
                pack = (num_pack.group("num") +
                        perl_to_python_packs[num_pack.group("char")])
            else:
                pack = perl_to_python_packs[pack]

            # If the field is an array then extract the length
            length = 1
            field_exp = re_array_field.match(field)
            if field_exp is not None:
                field = field_exp.group("field")
                length = num(field_exp.group("length"))

            structs[name][field] = StructField(pack, num(offset), printf,
                                               num(default), length)
        else:
            raise ValueError(
                "line {}: Invalid syntax in struct file".format(i))

    # Final check for setting size and base
    if structs[name].size is None:
        raise ValueError(
            "size value missing for struct '{}'".format(name))
    if structs[name].base is None:
        raise ValueError(
            "base value missing for struct '{}'".format(name))

    return structs


# Regex definitions
re_comment = re.compile(b"#.*$")
re_array_field = re.compile(b"(?P<field>\w+)\[(?P<length>\d+)\]")
re_numbered_pack = re.compile(b"(?P<char>\w)(?P<num>\d+)")
re_hex_num = re.compile(b"0(x|X)[0-9a-fA-F]+")


def num(value):
    """Convert a value from one of several bases to an int."""
    if re_hex_num.match(value):
        return int(value, base=16)
    else:
        return int(value)


class Struct(object):
    """Represents an instance of a struct.

    Elements in the struct are accessible by name, e.g., `struct[b"link_up"]`
    and are of type :py:class:`StructField`.

    Attributes
    ----------
    name : str
        Name of the struct.
    size : int
        Total size of the struct in bytes.
    base : int
        Base address of struct in memory.
    fields : {field_name: :py:class:`~.StructField`}
        Fields of the struct.
    """
    def __init__(self, name, size=None, base=None):
        self.name = name
        self.size = size
        self.base = base
        self.fields = dict()

    def update_default_values(self, **updates):
        """Replace the default values of specified fields.

        Parameters
        ----------
        Parameters are taken as keyword-arguments of `field=new_value`.

        Raises
        ------
        KeyError
            If a field doesn't exist in the struct.
        """
        for (field, value) in six.iteritems(updates):
            fname = six.b(field)
            self[fname] = self[fname]._replace(default=value)

    def __setitem__(self, name, field):
        """Set a field in the struct."""
        self.fields[name] = field

    def __getitem__(self, name):
        """Get a field in the struct."""
        return self.fields[name]

    def __contains__(self, name):
        return name in self.fields

    def pack(self):
        """Pack the struct (and its default values) into a string of bytes.

        Returns
        -------
        :py:class:`bytes`
            Byte-string representation of struct containing default values.
        """
        # Generate a buffer big enough to hold the packed values
        data = bytearray(b"\x00" * self.size)

        # Iterate over the fields, pack each value in little-endian format and
        # insert into the buffered data.
        for field in six.itervalues(self.fields):
            packed_data = struct.pack(b"<" + field.pack_chars, field.default)
            data[field.offset:len(packed_data)+field.offset] = packed_data

        return bytes(data)


StructField = collections.namedtuple("StructField",
                                     "pack_chars offset printf default length")


# Convert Perl struct packing characters to their Python equivalents
perl_to_python_packs = {
    b'A': b's',
    b'c': b'b',
    b'C': b'B',
    b'v': b'H',
    b'V': b'I',
}
