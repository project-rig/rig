import pytest

import trollius
from trollius import From, Return

from ..gather_fail import gather_fail


def test_gather_fail_success():

    @trollius.coroutine
    def return_arg_after_sleep(arg):
        yield From(trollius.sleep(arg))
        raise Return(arg)

    loop = trollius.get_event_loop()
    responses = loop.run_until_complete(gather_fail(
        return_arg_after_sleep(0.01),
        return_arg_after_sleep(0.02),
        return_arg_after_sleep(0.03),
        loop=loop))
    assert responses == [0.01, 0.02, 0.03]


def test_gather_fail_exception():

    class TestException(Exception):
        pass

    @trollius.coroutine
    def return_arg_after_sleep(arg):
        yield From(trollius.sleep(arg))
        raise Return(arg)

    @trollius.coroutine
    def raise_after_sleep(arg, exc):
        yield From(trollius.sleep(arg))
        raise exc

    loop = trollius.get_event_loop()
    with pytest.raises(TestException):
        loop.run_until_complete(gather_fail(
            return_arg_after_sleep(0.01),
            return_arg_after_sleep(0.02),
            raise_after_sleep(0.03, TestException()),
            loop=loop))
