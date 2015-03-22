"""Create a mock object which returns a future if async=True."""

from mock import Mock
import trollius


def future_mock(return_value=None):  # pramga: no cover
    """Create a mock object which when called returns a future with the
    specified value.

    This mock acts as if it is inside a LookBlockingMixin.look_blocking
    decorator, that is, it returns a result immediately if async=False and
    returns a result via a future if async=True.
    """
    def side_effect(*args, **kwargs):
        async = kwargs.pop("async", False)
        if async:
            fut = trollius.Future()
            fut.set_result(return_value)
            return fut
        else:
            return return_value

    return Mock(side_effect=side_effect)


def future_side_effect(side_effect):  # pragma: no cover
    """Create a mock object which has the specified side effect whose return
    value will be returned via a future.

    This mock acts as if it is inside a LookBlockingMixin.look_blocking
    decorator, that is, it returns a result immediately if async=False and
    returns a result via a future if async=True.
    """
    def new_side_effect(*args, **kwargs):
        async = kwargs.pop("async", False)
        try:
            return_value = side_effect(*args, **kwargs)
            if async:
                fut = trollius.Future()
                fut.set_result(return_value)
                return fut
            else:
                return return_value
        except Exception as e:
            if async:
                fut = trollius.Future()
                fut.set_exception(e)
                return fut
            else:
                raise

    return Mock(side_effect=new_side_effect)
