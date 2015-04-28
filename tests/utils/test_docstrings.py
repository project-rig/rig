import pytest

import functools

from enum import IntEnum

from rig.utils.docstrings import \
    add_int_enums_to_docstring, add_signature_to_docstring


def test_add_int_enums_to_docstring_empty():
    # With and without existing docstring
    @add_int_enums_to_docstring
    class EmptyIntEnum(IntEnum):
        pass

    @add_int_enums_to_docstring
    class EmptyIntEnumWithDocstring(IntEnum):
        """An empty IntEnum."""

    assert EmptyIntEnum.__doc__ == (
        "\n\n"
        "Attributes\n"
        "----------\n")
    assert EmptyIntEnumWithDocstring.__doc__ == (
        "An empty IntEnum.\n"
        "\n"
        "Attributes\n"
        "----------\n")


def test_add_int_enums_to_docstring():
    # With and without existing docstring
    @add_int_enums_to_docstring
    class MyIntEnum(IntEnum):
        a = 1
        b = 2

    @add_int_enums_to_docstring
    class MyIntEnumWithDocstring(IntEnum):
        """A populated IntEnum."""
        a = 1
        b = 2

    assert MyIntEnum.__doc__ == (
        "\n\n"
        "Attributes\n"
        "----------\n"
        "a = 1\n"
        "b = 2\n")
    assert MyIntEnumWithDocstring.__doc__ == (
        "A populated IntEnum.\n"
        "\n"
        "Attributes\n"
        "----------\n"
        "a = 1\n"
        "b = 2\n")


def wrap(f):
    """Return a transparent wrapper function around the supplied function."""
    @functools.wraps(f)
    def f_(*args, **kwargs):  # pragma: no cover
        return f(*args, **kwargs)
    return f_


def test_add_signature_to_docstring_empty():
    # With functions with no arguments, with-and-without a docstring

    def f():  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))

    def f_with_docstring():  # pragma: no cover
        """Example Function."""
        pass
    f_with_docstring_ = add_signature_to_docstring(f_with_docstring)(
        wrap(f_with_docstring))

    assert f_.__doc__ == "f()"
    assert f_with_docstring_.__doc__ == "f_with_docstring()\nExample Function."


@pytest.mark.parametrize("has_self", [True, False])
@pytest.mark.parametrize("self_has_default", [True, False])
@pytest.mark.parametrize("include_self", [True, False])
def test_add_signature_to_docstring_self(has_self,
                                         self_has_default,
                                         include_self):
    # Test that self is removed appropriately

    if self_has_default:
        def f(self=0, b=1, *c, **d):  # pragma: no cover
            pass
    elif has_self:
        def f(self, b=1, *c, **d):  # pragma: no cover
            pass
    else:
        def f(b=1, *c, **d):  # pragma: no cover
            pass
    f_ = add_signature_to_docstring(f, include_self=include_self)(wrap(f))

    if self_has_default:
        assert f_.__doc__ == "f(self=0, b=1, *c, **d)"
    elif include_self and has_self:
        assert f_.__doc__ == "f(self, b=1, *c, **d)"
    else:
        assert f_.__doc__ == "f(b=1, *c, **d)"


def test_add_signature_to_docstring_arguments():
    # Test generic sets of arguments

    def f():  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f()"

    def f(a):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f(a)"

    def f(a=0):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f(a=0)"

    def f(a, b):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f(a, b)"

    def f(a, b=1):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f(a, b=1)"

    def f(a=0, b=1):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f(a=0, b=1)"

    def f(a, b=1, *c, **d):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f(a, b=1, *c, **d)"


def test_add_signature_to_docstring_kw_only_args():
    # Test that keyword only arguments are added

    def f():  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f, kw_only_args={"a": 123})(wrap(f))
    assert f_.__doc__ == "f(*_, a=123)"

    # Make sure we can use our own varargs name
    def f(*b):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f, kw_only_args={"a": 123})(wrap(f))
    assert f_.__doc__ == "f(*b, a=123)"

    def f(b, *c, **d):  # pragma: no cover
        pass
    f_ = add_signature_to_docstring(f, kw_only_args={"a": 123})(wrap(f))
    assert f_.__doc__ == "f(b, *c, a=123, **d)"


def test_add_signature_to_docstring_no_override():
    # Test that if a signature is already in the docstring, it is not
    # overridden.

    def f():  # pragma: no cover
        """f(magic)"""
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f(magic)"

    # Test that if something which looks like a signature, but isn't, a
    # signature is added.

    def f():  # pragma: no cover
        """eff(magic)"""
        pass
    f_ = add_signature_to_docstring(f)(wrap(f))
    assert f_.__doc__ == "f()\neff(magic)"
