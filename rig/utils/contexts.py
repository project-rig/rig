"""Utilities for building contextual functions.

The MachineController has a lot of functions which take the same arguments,
many of which are contextual.  For example, when performing multiple operations
on a given chip::

    controller.sdram_alloc(1000, 1, x=3, y=2)
    controller.sdram_alloc(1000, 2, x=3, y=2)

Avoiding respecifying these arguments every time
will lead to cleaner and clearer code.  For example:

    with controller(app_id=32):
        with controller(x=1, y=1):
            controller.do_something(...)

        with controller(x=2, y=2):
            controller.do_something(...)

Is, in many cases, arguably clearer and less prone to silly mistakes than:

    controller.do_something(x=1, y=1, app_id=32)
    controller.do_something(x=2, y=2, app_id=32)

Though this form is still useful and should be allowed.

This module provides decorators for functions so that they can use contextual
arguments and a mixin for classes that provides a `get_new_context` method
which could be mapped to `__call__` to produce and use concepts as in the
previous example.
"""
import collections
import inspect
import functools
import sentinel
from six import iteritems

from rig.utils.docstrings import add_signature_to_docstring


Required = sentinel.create('Required')
"""Allow specifying keyword arguments as required, i.e., they must be satisfied
by either the context OR by the caller.

This is useful when a method has optional parameters and contextual arguments::

    @ContextMixin.use_contextual_arguments
    def sdram_alloc(self, size, tag=0, x=Required, y=Required):
        # ...
"""


class ContextMixin(object):
    """A mix-in which provides a context stack and allows querying of the stack
    to form keyword arguments.
    """
    def __init__(self, initial_context={}):
        """Create a context stack for this object.

        Parameters
        ----------
        initial_context : {kwarg: value}
            An initial set of contextual arguments mapping keyword to value.
        """
        self.__context_stack = collections.deque()
        self.__context_stack.append(Context(initial_context))

    def get_new_context(self, **kwargs):
        """Create a new context with the given keyword arguments."""
        return Context(kwargs, self.__context_stack)

    def update_current_context(self, **context_args):
        """Update the current context to contain new arguments."""
        self.__context_stack[-1].update(context_args)

    def get_context_arguments(self):
        """Return a dictionary containing the current context arguments."""
        cargs = {}
        for context in self.__context_stack:
            cargs.update(context.context_arguments)
        return cargs

    @staticmethod
    def use_contextual_arguments(f):
        """Decorator which modifies a function so that it is passed arguments
        from the call or from the current context.
        """
        # Build a list of keywords to get from the context
        arg_names, varargs, keywords, defaults = inspect.getargspec(f)
        kwargs = arg_names[-len(defaults):]  # names of the keyword arguments
        default_call = dict(zip(kwargs, defaults))

        # The signature-adding decorator is a work around sphinx autodoc +
        # Python 2 missing funcation signatures when functions are wrapped
        @add_signature_to_docstring(f)
        @functools.wraps(f)
        def f_(*args, **kwargs):
            self = args[0]
            # Bind all arguments with their names
            kwargs.update(dict(zip(arg_names[1:], args[1:])))

            # Update the arguments using values from the context
            cargs = self.get_context_arguments()
            calls = {k: cargs.get(k, v) for (k, v) in iteritems(default_call)}

            # Update the arguments using values from the call
            calls = {k: kwargs.get(k, v) for (k, v) in iteritems(calls)}

            # Raise a TypeError if any `Required` sentinels remain
            for k, v in iteritems(calls):
                if v is Required:
                    raise TypeError(
                        "{!s}: missing argument {}".format(f.__name__, k))

            # Update the keyword arguments
            kwargs.update(calls)
            return f(self, **kwargs)

        return f_

    @staticmethod
    def use_named_contextual_arguments(**named_arguments):
        """Decorator which modifies a function such that it is passed arguments
        given by the call and named arguments from the call or from the
        context.

        Parameters
        ----------
        **named_arguments : {name: default, ...}
            All named arguments are given along with their default value.
        """
        def decorator(f):
            # Update the docstring signature to include the specified arguments
            @add_signature_to_docstring(f, kw_only_args=named_arguments)
            @functools.wraps(f)
            def f_(self, *args, **kwargs):
                # Construct the list of required arguments, update using the
                # context arguments and the kwargs passed to the method.
                new_kwargs = named_arguments.copy()

                cargs = self.get_context_arguments()
                for name, val in iteritems(cargs):
                    if name in new_kwargs:
                        new_kwargs[name] = val

                new_kwargs.update(kwargs)

                # Raise a TypeError if any `Required` sentinels remain
                for k, v in iteritems(new_kwargs):
                    if v is Required:
                        raise TypeError(
                            "{!s}: missing argument {}".format(f.__name__, k))

                return f(self, *args, **new_kwargs)
            return f_

        return decorator


class Context(object):
    """A context object that stores arguments that may be passed to
    functions.
    """
    def __init__(self, context_arguments, stack=None):
        """Create a new context object that can be added to a stack.

        Parameters
        ----------
        context_arguments : {kwarg: value}
            A dict of contextual arguments mapping keyword to value.
        stack : :py:class:`deque`
            Context stack to which this context will append itself when
            entered.
        """
        self.context_arguments = dict(context_arguments)
        self.stack = stack
        self._before_close = list()

    def update(self, updates):
        """Update the arguments contained within this context."""
        self.context_arguments.update(updates)

    def before_close(self, *args):
        """Call the given function(s) before this context is exited."""
        for fn in args:
            self._before_close.append(fn)

    def __enter__(self):
        # Add this context object to the stack
        self.stack.append(self)

    def __exit__(self, exception_type, exception_value, traceback):
        try:
            # Call all the passed functions before closing the context
            for fn in self._before_close:
                fn()
        finally:
            # Remove self from the stack
            assert self.stack.pop() is self
