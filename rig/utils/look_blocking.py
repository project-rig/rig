"""Mixin which makes internally-asynchronous code optionally look blocking.

Rig contains objects such as MachineController and BMPController which are
required to deal with complex and (ideally...) high-performance I/O. To
facilitate this, they are implemented in a non-blocking style powered by the
Trollius library (the Python 2 asyncio backport).

For many applications, the interface such an implementation presents is
needlessly complex and so it is desireable to present a blocking, synchronous
interface for the average user. At the same time, methods in these classes may
wish to call other methods and to do so in a non-blocking style. Further,
certain applications may wish to implement their own non-blocking code. As a
result, presenting a non-blocking API is also neccessary.

A simple wrapper is all that is required to make an asynchronous method behave
like a blocking function and so the primary contribution of this mixin is to
provide a decorator which by default makes methods behave in a blocking style.
In order to support the non-blocking style, the decorator has an optional
keyword argument `async` which when set to True results in the native
non-blocking behaviour being exposed.

The secondary contribution of this mixin is to enforce the storage of a
reference to the event loop in use. Further, the mixin automatically creates
such an event loop if one is not provided further hiding any asynchronous magic
to users who do not wish to use it.

.. Warning::
    All documentation refers to :py:mod:`asyncio` even though this
    implementation uses Trollius for Python 2 compatibility. This is because
    the Trollius API is identical to that of :py:mod:`asyncio` and is the
    recommended source of documentation.
"""

import trollius

import functools


class LookBlockingMixin(object):
    """Mixin which makes internally-asynchronous code optionally look blocking.
    
    Example usage::
    
        class MyClass(LookBlockingMixin):
            def __init__(self, loop=None):
                LookBlockingMixin.__init__(self, loop)
            
            @LookBlockingMixin.look_blocking
            @trollius.coroutine
            def sleep_and_return_arg(self, arg):
                # Coroutine: returns its argument after a 2 second delay.
                yield From(trollius.sleep(2.0, loop=self.loop))
                raise Return(arg)
    
    For users who wish to use MyClass in a blocking fashion::
        
        >>> c = MyClass()
        >>> c.sleep_and_return_arg(123)
        # After two seconds...
        123
    
    For users who wish to work in a non-blocking style::
    
        >>> # Users can optionally provide their own event loop
        >>> loop = trollius.get_event_loop()
        >>> c = MyClass(loop=loop)
        >>> loop.run_until_complete(trollius.gather(
        ...     c.sleep_and_return_arg(123, async=True),
        ...     c.sleep_and_return_arg(456, async=True),
        ...     c.sleep_and_return_arg(789, async=True), loop=loop))
        # After two seconds...
        [123, 456, 789]
    """

    def __init__(self, loop=None):
        """Store a reference to the event loop in use.

        Parameters
        ----------
        loop : :py:class:`asyncio.BaseEventLoop` or None
            The event loop to use. If None, :py:func:`asyncio.get_event_loop`
            will be used to get a suitable event loop.
        """
        if loop is None:
            loop = trollius.get_event_loop()
        self.loop = loop

    @staticmethod
    def look_blocking(f):
        """Decorator which makes a coroutine function/future-returning function
        (optionally) block until the coroutine/future completes.

        The decorator adds an additional `async` keyword argument to any
        decorated function which defaults to False. If the argument is False,
        the function will block as described above. If True, the
        coroutine/future will be returned instead.
        """
        @functools.wraps(f)
        def f_(*args, **kwargs):
            self = args[0]

            if kwargs.pop("async", False):
                # Directly expose the async interface
                return f(*args, **kwargs)
            else:
                # Block until the coroutine/future completes
                return self.loop.run_until_complete(f(*args, **kwargs))

        return f_
