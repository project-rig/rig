"""Docstring manipulation functions.

These functions are generally work-arounds to fix deficiencies in Sphinx's
autodoc capabilities.
"""

import inspect

from six import iteritems


def add_int_enums_to_docstring(enum):
    """Decorator for IntEnum which re-writes the documentation string so that
    Sphinx enumerates all the enumeration values.

    This is a work-around for Sphinx autodoc's inability to properly document
    IntEnums.

    This decorator adds enumeration names and values to the 'Attributes'
    section of the docstring of the decorated IntEnum class.

    Example::

        >>> from enum import IntEnum
        >>> @add_int_enums_to_docstring
        ... class MyIntEnum(IntEnum):
        ...     '''An example IntEnum.'''
        ...     a = 0
        ...     b = 1
        >>> print(MyIntEnum.__doc__)
        An example IntEnum.
        <BLANKLINE>
        Attributes
        ----------
        a = 0
        b = 1
        <BLANKLINE>
    """
    # The enum34 library (used for compatibility with Python < v3.4) rather
    # oddly set its docstring to None rather than some senible but empty
    # default...
    if enum.__doc__ is None:  # pragma: nocover
        enum.__doc__ = ""

    enum.__doc__ += ("\n\n"
                     "Attributes\n"
                     "----------\n")
    for val in list(enum):
        enum.__doc__ += "{} = {}\n".format(val.name, int(val))

    return enum


def add_signature_to_docstring(f, include_self=False, kw_only_args={}):
    """Decorator which adds the function signature of 'f' to the decorated
    function's docstring.

    Under Python 2, wrapping a function (even using functools.wraps) hides its
    signature to Sphinx's introspection tools so it is necessary to include the
    function signature in the docstring to enable Sphinx to render it
    correctly.

    Additionally, when building decorators which change a function's signature,
    it is non-trivial modify the wrapper's function signature and so
    automatically generated documentation will not display the correct
    signature. This decorator can aid in the specific case where a wrapper adds
    keyword-only arguments to the set of arguments accepted by the underlying
    function.

    For example::

        >>> def my_func(a, b=0, *args, **kwargs):
        ...     '''An example function.'''
        ...     pass

        >>> import functools
        >>> @add_signature_to_docstring(my_func, kw_only_args={"c": 1})
        ... @functools.wraps(my_func)
        ... def my_func_wrapper(*args, **kwargs):
        ...     c = kwargs.pop("c")
        ...     # ...do something with c...
        ...     return my_func(*args, **kwargs)
        >>> print(my_func_wrapper.__doc__)
        my_func(a, b=0, *args, c=1, **kwargs)
        An example function.

    .. warning::
        This function only works with functions which do not have any
        named keyword-only arguments. For example this function cannot be
        handled::

            def f(*args, kw_only_arg=123)

        This is due to a limitation in the underlying introspection library
        provided in Python 2.

    Parameters
    ----------
    f : function
        The function whose signature will be used. Need not be the same as the
        decorated function.
    include_self : bool
        Should an initial 'self' arguments be included in the signature? (These
        are assumed to be arguments called 'self' without a default value).
    kw_only_args : dict
        Optionally, add a set of keyword-only arguments to the function
        signature. This is useful if the wrapper function adds new keyword-only
        arguments.
    """

    def decorate(f_wrapper):
        args, varargs, keywords, defaults = inspect.getargspec(f)

        # Simplifies later logic
        if defaults is None:
            defaults = []

        # Make sure the keyword only arguments don't use the names of any other
        # arguments
        assert set(args).isdisjoint(set(kw_only_args))
        assert varargs is None or varargs not in kw_only_args
        assert keywords is None or keywords not in kw_only_args

        # If required, remove the initial 'self' argument (e.g. for methods)
        if not include_self:
            if (len(args) >= 1 and
                    args[0] == "self" and
                    len(args) > len(defaults)):
                args.pop(0)

        # Assemble a string representation of the signature. This must be done
        # by hand (rather than using formatargspec) to allow the assembly of
        # signatures with keyword-only values.
        signature = "{}(".format(f_wrapper.__name__)
        for arg in args[:-len(defaults)] if defaults else args:
            signature += "{}, ".format(arg)
        for arg, default in zip(args[-len(defaults):], defaults):
            signature += "{}={}, ".format(arg, repr(default))
        if kw_only_args or varargs is not None:
            # Must include a varargs name if keyword only arguments are
            # supplied.
            if varargs is None and kw_only_args:
                assert "_" not in args
                assert "_" not in kw_only_args
                assert "_" != keywords
                signature += "*_, "
            else:
                signature += "*{}, ".format(varargs)
        for keyword, default in iteritems(kw_only_args):
            signature += "{}={}, ".format(keyword, default)
        if keywords is not None:
            signature += "**{}, ".format(keywords)
        signature = "{})".format(signature.rstrip(", "))

        # Only add the signature if one is not already present.
        if f_wrapper.__doc__ is None:
            f_wrapper.__doc__ = signature
        elif not f_wrapper.__doc__.lstrip().startswith(
                "{}(".format(f_wrapper.__name__)):
            f_wrapper.__doc__ = "{}\n{}".format(signature, f_wrapper.__doc__)

        # Return the original function (after modifying its __doc__)
        return f_wrapper

    return decorate
