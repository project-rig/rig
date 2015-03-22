"""A gather coroutine which ensures all results are collected while throwing an
exception if some fail."""

import trollius
from trollius import From, Return


@trollius.coroutine
def gather_fail(*coros_or_futures, **kwargs):
    """Return a list of results of the specified coroutines, throwing an
    exception if any fail.

    This wrapper around :py:func:`asyncio.gather` waits for all
    coroutines/futures to complete (either successfully or with an exception)
    and, if non returned an exception, a list of results is produced. If an
    exception occurred, the exception produced coroutine/future which failed is
    raised.
    """
    loop = kwargs.pop("loop", None)
    assert kwargs == {}, "No keyword args eccept 'loop' expected."""

    responses = yield From(trollius.gather(*coros_or_futures,
                                           loop=loop,
                                           return_exceptions=True))
    # If something went wrong, die
    for response in responses:
        if isinstance(response, Exception):  # pragma: no cover
            raise response

    # Otherwise, return the responses
    raise Return(responses)
