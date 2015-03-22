import pytest

from ..look_blocking import LookBlockingMixin

import trollius
from trollius import From, Return


class MyException(Exception):
    pass


class MyClass(LookBlockingMixin):
    """A test class with a single async method."""

    def __init__(self, loop):
        LookBlockingMixin.__init__(self, loop)

    @LookBlockingMixin.look_blocking
    @trollius.coroutine
    def coro_sleep_and_return_arg(self, arg):
        """Coroutine: returns its argument after a delay."""
        yield From(trollius.sleep(0.01, loop=self.loop))
        raise Return(arg)

    @LookBlockingMixin.look_blocking
    def fut_sleep_and_return_arg(self, arg):
        """Returns a future which returns its value after a delay."""
        fut = trollius.Future(loop=self.loop)

        def satisfy():
            if not fut.cancelled():  # pragma: no branch
                fut.set_result(arg)
        self.loop.call_later(0.01, satisfy)
        return fut

    @LookBlockingMixin.look_blocking
    @trollius.coroutine
    def coro_sleep_and_raise(self):
        """Coroutine: raise an MyException exception after a delay."""
        yield From(trollius.sleep(0.01, loop=self.loop))
        raise MyException("I woke up on the wrong side of the bed!")

    @LookBlockingMixin.look_blocking
    @trollius.coroutine
    def fut_sleep_and_raise(self):
        """Return a future which raises a MyException exception after a delay
        """
        fut = trollius.Future(loop=self.loop)

        def fail():
            if not fut.cancelled():  # pragma: no branch
                fut.set_exception(MyException("I don't want to wake up!"))
        self.loop.call_later(0.01, fail)
        return fut


@pytest.mark.parametrize("supplied_loop", [None, trollius.new_event_loop()])
def test_look_blocking(supplied_loop):
    t = MyClass(supplied_loop)

    # Make sure the blocking interfaces work
    assert t.coro_sleep_and_return_arg(123) == 123
    assert t.fut_sleep_and_return_arg(456) == 456
    with pytest.raises(MyException):
        t.coro_sleep_and_raise()
    with pytest.raises(MyException):
        t.fut_sleep_and_raise()

    # Make sure the non-blocking interfaces work
    assert t.loop.run_until_complete(
        t.coro_sleep_and_return_arg(123, async=True)) == 123
    assert t.loop.run_until_complete(
        t.fut_sleep_and_return_arg(456, async=True)) == 456
    with pytest.raises(MyException):
        t.loop.run_until_complete(t.coro_sleep_and_raise(async=True))
    with pytest.raises(MyException):
        t.loop.run_until_complete(t.fut_sleep_and_raise(async=True))
